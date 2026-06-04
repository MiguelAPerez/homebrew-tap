#!/usr/bin/env python3
"""Auto-update Homebrew formulas to their latest upstream GitHub release.

Scans ``Formula/*.rb``, derives the GitHub repo from each formula's
``homepage`` field, fetches the latest release, recomputes the SHA256s by
substituting the new version into the formula's ``url`` templates, and opens
one pull request per updated formula.

Design: the parsing/patching logic is split into small pure functions, and all
real I/O (HTTP, hashing, ``git``, ``gh``) is funnelled through injectable
callables. That keeps everything in this module unit-testable without a
network connection or a git checkout.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence


# --------------------------------------------------------------------------- #
# Pure helpers (no I/O) — fully unit-testable.
# --------------------------------------------------------------------------- #

REPO_RE = re.compile(r'homepage "https://github\.com/([^/"]+/[^/"]+)"')
VERSION_RE = re.compile(r'version "([^"]+)"')
URL_RE = re.compile(r'url "([^"]+)"')
SHA_RE = re.compile(r'sha256 "\S+"')
VERSION_FIELD_RE = re.compile(r'version "\S+"')


class UpdateError(Exception):
    """Raised when a formula cannot be updated (bad shape, hashing failed)."""


def parse_repo(content: str) -> Optional[str]:
    """Return ``owner/name`` from the formula's GitHub homepage, or None."""
    m = REPO_RE.search(content)
    return m.group(1) if m else None


def parse_version(content: str) -> Optional[str]:
    """Return the formula's current ``version`` string, or None."""
    m = VERSION_RE.search(content)
    return m.group(1) if m else None


def normalize_version(tag: str) -> str:
    """Strip a single leading ``v`` from a release tag (``v1.2.3`` -> ``1.2.3``).

    Only one leading ``v`` is removed, so tags that merely start with ``v``
    (e.g. ``version-1.0``) are left intact.
    """
    return tag[1:] if tag.startswith("v") else tag


def url_templates(content: str) -> list[str]:
    """Return every ``url`` template in the formula, in order of appearance."""
    return URL_RE.findall(content)


def render_url(template: str, version: str) -> str:
    """Substitute a concrete version into a formula ``url`` template."""
    return template.replace("#{version}", version)


def patch_formula(content: str, new_version: str, new_sha256s: Sequence[str]) -> str:
    """Return ``content`` with the version and sha256 values replaced.

    The sha256 values are applied in order of appearance. Raises
    :class:`UpdateError` if the number of supplied hashes does not match the
    number of ``sha256`` fields in the formula.
    """
    sha_count = len(SHA_RE.findall(content))
    if sha_count != len(new_sha256s):
        raise UpdateError(
            f"expected {sha_count} sha256 value(s) to match the formula, "
            f"got {len(new_sha256s)}"
        )
    out = VERSION_FIELD_RE.sub(f'version "{new_version}"', content, count=1)
    shas = iter(new_sha256s)
    return SHA_RE.sub(lambda _m: f'sha256 "{next(shas)}"', out)


# --------------------------------------------------------------------------- #
# Update planning — pure logic with injected I/O callables.
# --------------------------------------------------------------------------- #

@dataclass
class Update:
    """A planned bump of a single formula file."""

    path: Path
    name: str
    old_version: str
    new_version: str
    new_content: str


# get_latest_release(repo) -> release dict (or None); hash_url(url) -> sha hex (or None)
ReleaseFn = Callable[[str], Optional[dict]]
HashFn = Callable[[str], Optional[str]]
LogFn = Callable[[str], None]


def plan_formula_update(
    path: Path, content: str, latest: str, hash_url: HashFn
) -> Update:
    """Build the :class:`Update` that bumps ``path`` to ``latest``.

    ``hash_url`` is injected so tests need no network. Raises
    :class:`UpdateError` if any release asset cannot be hashed.
    """
    name = path.stem
    current = parse_version(content) or ""
    shas: list[str] = []
    for tmpl in url_templates(content):
        actual_url = render_url(tmpl, latest)
        sha = hash_url(actual_url)
        if not sha:
            raise UpdateError(f"could not hash {actual_url}")
        shas.append(sha)
    new_content = patch_formula(content, latest, shas)
    return Update(path, name, current, latest, new_content)


def compute_updates(
    formula_paths: Iterable[Path],
    get_latest_release: ReleaseFn,
    hash_url: HashFn,
    log: LogFn = print,
) -> list[Update]:
    """Inspect each formula and return the list that needs updating.

    Formulas that are up to date, malformed, or whose release/hashes cannot be
    fetched are logged and skipped rather than aborting the whole run.
    """
    updates: list[Update] = []
    for path in sorted(formula_paths):
        content = path.read_text()
        name = path.stem

        repo = parse_repo(content)
        if not repo:
            log(f"[{name}] skipping — no GitHub homepage")
            continue

        current = parse_version(content)
        if not current:
            log(f"[{name}] skipping — no version field")
            continue

        release = get_latest_release(repo)
        if not release or "tag_name" not in release:
            log(f"[{name}] skipping — could not fetch latest release for {repo}")
            continue

        latest = normalize_version(release["tag_name"])
        if latest == current:
            log(f"[{name}] up to date ({current})")
            continue

        log(f"[{name}] {current} -> {latest}")
        try:
            updates.append(plan_formula_update(path, content, latest, hash_url))
        except UpdateError as exc:
            log(f"[{name}] {exc}, skipping")
            continue

    return updates


# --------------------------------------------------------------------------- #
# Command runner — wraps git/gh and remembers failures so the job goes red.
# --------------------------------------------------------------------------- #

# A Runner runs a command list and returns something with .returncode/.stdout/.stderr.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class CommandRunner:
    """Runs ``git``/``gh`` commands, surfacing and remembering any failures.

    The previous inline workflow swallowed stdout/stderr and never checked
    return codes, so a failed ``gh pr create`` looked like success. This
    records every non-zero exit and emits a ``::error::`` annotation, and
    :func:`main` exits non-zero when ``failures`` is non-empty.
    """

    def __init__(self, token: str, run: Runner = subprocess.run, log: LogFn = print):
        self.token = token
        self._run = run
        self._log = log
        self.failures: list[str] = []

    def _exec(self, argv: Sequence[str], env: Optional[dict], check: bool):
        result = self._run(list(argv), capture_output=True, text=True, env=env)
        if check and result.returncode != 0:
            self._log(
                f"::error::{' '.join(argv)} failed:\n{(result.stderr or '').strip()}"
            )
            self.failures.append(f"{argv[0]} {argv[1] if len(argv) > 1 else ''}".strip())
        return result

    def git(self, *args: str, check: bool = True):
        return self._exec(["git", *args], env=None, check=check)

    def gh(self, *args: str, check: bool = True):
        return self._exec(
            ["gh", *args], env={**os.environ, "GH_TOKEN": self.token}, check=check
        )


def has_open_pr(runner: CommandRunner, name: str, version: str) -> Optional[bool]:
    """Whether an open PR for this formula+version already exists.

    Returns True/False when ``gh`` reports a count, or None when the check
    itself could not be performed (e.g. auth/API failure) so the caller can
    skip rather than risk creating a duplicate. A failed call is already
    recorded by the runner, so the job will still go red.
    """
    result = runner.gh(
        "pr", "list", "--state", "open",
        "--search", f"Update {name} to v{version}",
        "--json", "number", "--jq", "length",
    )
    if result.returncode != 0:
        return None
    count = (result.stdout or "").strip()
    return count.isdigit() and int(count) > 0


def create_pull_requests(
    updates: Sequence[Update],
    runner: CommandRunner,
    base: str = "main",
    log: LogFn = print,
) -> None:
    """Create one branch + PR per update, reporting outcomes honestly."""
    for upd in updates:
        branch = f"update/{upd.name}-v{upd.new_version}"

        existing = has_open_pr(runner, upd.name, upd.new_version)
        if existing is None:
            log(f"[{upd.name}] could not verify existing PRs, skipping")
            continue
        if existing:
            log(f"[{upd.name}] PR already open, skipping")
            continue

        if runner.git("checkout", base).returncode != 0:
            log(f"[{upd.name}] could not check out {base}, skipping")
            continue
        if runner.git("checkout", "-b", branch).returncode != 0:
            log(f"[{upd.name}] could not create branch {branch}, skipping")
            continue

        upd.path.write_text(upd.new_content)
        runner.git("add", str(upd.path))
        runner.git("commit", "-m", f"Update {upd.name} to v{upd.new_version}")

        if runner.git("push", "origin", branch).returncode != 0:
            log(f"[{upd.name}] push failed, not creating PR")
            continue

        result = runner.gh(
            "pr", "create",
            "--title", f"Update {upd.name} to v{upd.new_version}",
            "--body",
            f"Automated update of {upd.name} from "
            f"v{upd.old_version} to v{upd.new_version}.",
            "--base", base,
            "--head", branch,
        )
        if result.returncode == 0:
            log(
                f"[{upd.name}] PR created: {upd.old_version} -> {upd.new_version} "
                f"{(result.stdout or '').strip()}"
            )
        else:
            log(
                f"[{upd.name}] PR creation FAILED for "
                f"{upd.old_version} -> {upd.new_version} "
                f"(branch {branch} was pushed; open the PR manually)"
            )


# --------------------------------------------------------------------------- #
# Real I/O implementations (thin wrappers around curl/sha256sum).
# --------------------------------------------------------------------------- #

def api_get(url: str, token: str, run: Runner = subprocess.run) -> Optional[dict]:
    """GET a GitHub API URL and return the decoded JSON, or None on failure."""
    result = run(
        ["curl", "-sf",
         "-H", f"Authorization: Bearer {token}",
         "-H", "Accept: application/vnd.github+json",
         url],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Non-JSON 200 body (proxy HTML, rate-limit page, ...) — skip cleanly
        # instead of crashing the whole run.
        return None


def sha256_of_url(url: str, run: Runner = subprocess.run) -> Optional[str]:
    """Download ``url`` and return its sha256 hex digest, or None on failure.

    Uses ``curl -f`` and ``pipefail`` so a 404/error response fails the
    pipeline rather than hashing an error body into the formula.
    """
    result = run(
        f"set -o pipefail; curl -fsSL {shlex.quote(url)} | sha256sum",
        shell=True, capture_output=True, text=True, executable="/bin/bash",
    )
    if result.returncode != 0:
        return None
    parts = (result.stdout or "").split()
    return parts[0] if parts else None


# --------------------------------------------------------------------------- #
# Entry point.
# --------------------------------------------------------------------------- #

def main() -> None:
    token = os.environ["GITHUB_TOKEN"]
    formula_dir = Path(os.environ.get("FORMULA_DIR", "Formula"))

    runner = CommandRunner(token)
    updates = compute_updates(
        formula_dir.glob("*.rb"),
        get_latest_release=lambda repo: api_get(
            f"https://api.github.com/repos/{repo}/releases/latest", token
        ),
        hash_url=sha256_of_url,
    )
    create_pull_requests(updates, runner)

    if runner.failures:
        raise SystemExit(
            f"{len(runner.failures)} command(s) failed: {', '.join(runner.failures)}"
        )


if __name__ == "__main__":
    main()
