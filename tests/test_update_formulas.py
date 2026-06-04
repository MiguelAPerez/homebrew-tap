"""Unit tests for scripts/update_formulas.py.

All I/O (HTTP, hashing, git, gh) is faked, so these run offline and fast.
"""
import subprocess
from pathlib import Path

import pytest

import update_formulas as uf


FORMULA = """\
class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.1.2"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    end
  end

  def install
    bin.install "openstash"
  end
end
"""


# --- pure helpers ----------------------------------------------------------- #

def test_parse_repo():
    assert uf.parse_repo(FORMULA) == "MiguelAPerez/openstash"


def test_parse_repo_missing():
    assert uf.parse_repo('homepage "https://example.com/x"') is None


def test_parse_version():
    assert uf.parse_version(FORMULA) == "0.1.2"


@pytest.mark.parametrize("tag,expected", [
    ("v1.2.3", "1.2.3"),
    ("1.2.3", "1.2.3"),
    ("vv1.2.3", "v1.2.3"),  # only ONE leading "v" is removed (not a greedy lstrip)
])
def test_normalize_version(tag, expected):
    assert uf.normalize_version(tag) == expected


def test_url_templates_in_order():
    tmpls = uf.url_templates(FORMULA)
    assert len(tmpls) == 2
    assert tmpls[0].endswith("darwin_arm64.tar.gz")
    assert tmpls[1].endswith("darwin_amd64.tar.gz")


def test_render_url_substitutes_version():
    tmpl = 'https://x/releases/download/v#{version}/a_#{version}.tar.gz'
    assert uf.render_url(tmpl, "9.9.9") == "https://x/releases/download/v9.9.9/a_9.9.9.tar.gz"


def test_patch_formula_replaces_version_and_shas_in_order():
    out = uf.patch_formula(FORMULA, "0.2.0", ["1" * 64, "2" * 64])
    assert 'version "0.2.0"' in out
    assert 'version "0.1.2"' not in out
    # order preserved: first sha goes to the arm64 (first) block
    arm_idx = out.index("darwin_arm64")
    amd_idx = out.index("darwin_amd64")
    assert out.index("1" * 64) < arm_idx + 200  # the "1" sha sits right after arm url
    assert out.index("2" * 64) > arm_idx
    assert out.index("2" * 64) < amd_idx + 200


def test_patch_formula_rejects_sha_count_mismatch():
    with pytest.raises(uf.UpdateError):
        uf.patch_formula(FORMULA, "0.2.0", ["1" * 64])  # formula has 2 sha fields


# --- planning --------------------------------------------------------------- #

def test_plan_formula_update_hashes_each_url():
    seen = []

    def fake_hash(url):
        seen.append(url)
        return f"{len(seen):064d}"

    upd = uf.plan_formula_update(Path("Formula/openstash.rb"), FORMULA, "0.2.0", fake_hash)

    assert upd.name == "openstash"
    assert upd.old_version == "0.1.2"
    assert upd.new_version == "0.2.0"
    assert 'version "0.2.0"' in upd.new_content
    assert all("v0.2.0" in u for u in seen)  # version substituted before hashing
    assert len(seen) == 2


def test_plan_formula_update_raises_when_hash_fails():
    with pytest.raises(uf.UpdateError):
        uf.plan_formula_update(Path("x.rb"), FORMULA, "0.2.0", lambda url: None)


def _write_formula(tmp_path, content=FORMULA):
    d = tmp_path / "Formula"
    d.mkdir()
    (d / "openstash.rb").write_text(content)
    return d


def test_compute_updates_finds_newer_release(tmp_path):
    d = _write_formula(tmp_path)
    logs = []
    updates = uf.compute_updates(
        d.glob("*.rb"),
        get_latest_release=lambda repo: {"tag_name": "v0.2.0"},
        hash_url=lambda url: "c" * 64,
        log=logs.append,
    )
    assert len(updates) == 1
    assert updates[0].new_version == "0.2.0"
    assert "[openstash] 0.1.2 -> 0.2.0" in logs


def test_compute_updates_skips_when_up_to_date(tmp_path):
    d = _write_formula(tmp_path)
    logs = []
    updates = uf.compute_updates(
        d.glob("*.rb"),
        get_latest_release=lambda repo: {"tag_name": "0.1.2"},
        hash_url=lambda url: pytest.fail("should not hash when up to date"),
        log=logs.append,
    )
    assert updates == []
    assert any("up to date" in m for m in logs)


def test_compute_updates_skips_when_release_unavailable(tmp_path):
    d = _write_formula(tmp_path)
    logs = []
    updates = uf.compute_updates(
        d.glob("*.rb"),
        get_latest_release=lambda repo: None,
        hash_url=lambda url: "c" * 64,
        log=logs.append,
    )
    assert updates == []
    assert any("could not fetch latest release" in m for m in logs)


def test_compute_updates_skips_formula_without_homepage(tmp_path):
    d = tmp_path / "Formula"
    d.mkdir()
    (d / "bad.rb").write_text('class Bad < Formula\n  version "1.0"\nend\n')
    logs = []
    updates = uf.compute_updates(
        d.glob("*.rb"),
        get_latest_release=lambda repo: pytest.fail("should not query release"),
        hash_url=lambda url: "c" * 64,
        log=logs.append,
    )
    assert updates == []
    assert any("no GitHub homepage" in m for m in logs)


# --- command runner & PR flow ----------------------------------------------- #

class FakeRun:
    """Stand-in for subprocess.run that returns scripted results and records calls."""

    def __init__(self, results):
        # results: dict mapping a substring of the first arg -> (returncode, stdout, stderr)
        self.results = results
        self.calls = []

    def __call__(self, argv, capture_output=True, text=True, env=None,
                 shell=False, executable=None):
        self.calls.append(argv)
        key = argv if isinstance(argv, str) else " ".join(argv)
        for needle, (rc, out, err) in self.results.items():
            if needle in key:
                return subprocess.CompletedProcess(argv, rc, out, err)
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_command_runner_records_failure_and_annotates():
    logs = []
    run = FakeRun({"pr create": (1, "", "Actions not permitted to create PRs")})
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    result = runner.gh("pr", "create", "--title", "x")

    assert result.returncode == 1
    assert runner.failures == ["gh pr"]
    assert any("::error::" in m and "Actions not permitted" in m for m in logs)


def test_command_runner_success_records_nothing():
    runner = uf.CommandRunner("tok", run=FakeRun({}), log=lambda _m: None)
    assert runner.git("status").returncode == 0
    assert runner.failures == []


def test_has_open_pr_true_and_false():
    open_runner = uf.CommandRunner("t", run=FakeRun({"pr list": (0, "1\n", "")}), log=lambda _m: None)
    none_runner = uf.CommandRunner("t", run=FakeRun({"pr list": (0, "0\n", "")}), log=lambda _m: None)
    assert uf.has_open_pr(open_runner, "openstash", "0.2.0") is True
    assert uf.has_open_pr(none_runner, "openstash", "0.2.0") is False


def test_has_open_pr_returns_none_when_check_fails():
    runner = uf.CommandRunner("t", run=FakeRun({"pr list": (1, "", "API down")}), log=lambda _m: None)
    assert uf.has_open_pr(runner, "openstash", "0.2.0") is None
    assert runner.failures == ["gh pr"]  # recorded -> job goes red


def test_create_pull_requests_happy_path(tmp_path):
    f = tmp_path / "openstash.rb"
    f.write_text(FORMULA)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA.replace("0.1.2", "0.2.0"))

    logs = []
    run = FakeRun({
        "pr list": (0, "0\n", ""),
        "pr create": (0, "https://github.com/x/y/pull/42\n", ""),
    })
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert runner.failures == []
    assert f.read_text() == FORMULA.replace("0.1.2", "0.2.0")  # file was written
    assert any("PR created" in m and "pull/42" in m for m in logs)
    # the branch name is derived from the formula + version
    assert any("checkout" in " ".join(c) and "update/openstash-v0.2.0" in " ".join(c)
               for c in run.calls)


def test_create_pull_requests_reports_failure_loudly(tmp_path):
    """Regression test: a failed `gh pr create` must NOT look like success."""
    f = tmp_path / "openstash.rb"
    f.write_text(FORMULA)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA)

    logs = []
    run = FakeRun({
        "pr list": (0, "0\n", ""),
        "pr create": (1, "", "GitHub Actions is not permitted to create or approve pull requests"),
    })
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert runner.failures == ["gh pr"]  # so main() will exit non-zero
    assert any("PR creation FAILED" in m for m in logs)
    assert not any("PR created" in m for m in logs)


def test_create_pull_requests_skips_when_pr_already_open(tmp_path):
    f = tmp_path / "openstash.rb"
    f.write_text(FORMULA)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA)

    logs = []
    run = FakeRun({"pr list": (0, "1\n", "")})
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert any("already open" in m for m in logs)
    assert not any("checkout" in " ".join(c) for c in run.calls)  # no branch work


def test_create_pull_requests_skips_when_pr_check_unverifiable(tmp_path):
    """If `gh pr list` fails we must not branch/commit/push blindly."""
    f = tmp_path / "openstash.rb"
    f.write_text(FORMULA)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA)

    logs = []
    run = FakeRun({"pr list": (1, "", "API down")})
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert runner.failures == ["gh pr"]  # job goes red
    assert any("could not verify existing PRs" in m for m in logs)
    assert not any("checkout" in " ".join(c) for c in run.calls)  # no branch work


def test_create_pull_requests_skips_when_checkout_fails(tmp_path):
    """A failed checkout must abort before writing/committing/pushing."""
    f = tmp_path / "openstash.rb"
    original = FORMULA
    f.write_text(original)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA.replace("0.1.2", "0.2.0"))

    logs = []
    run = FakeRun({"pr list": (0, "0\n", ""), "checkout": (1, "", "cannot checkout")})
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert runner.failures == ["git checkout"]
    assert f.read_text() == original  # file was NOT modified
    assert any("could not check out" in m for m in logs)
    assert not any("commit" in " ".join(c) for c in run.calls)
    assert not any("push" in " ".join(c) for c in run.calls)


def test_create_pull_requests_skips_pr_when_push_fails(tmp_path):
    f = tmp_path / "openstash.rb"
    f.write_text(FORMULA)
    upd = uf.Update(f, "openstash", "0.1.2", "0.2.0", FORMULA)

    logs = []
    run = FakeRun({"pr list": (0, "0\n", ""), "push": (1, "", "denied")})
    runner = uf.CommandRunner("tok", run=run, log=logs.append)

    uf.create_pull_requests([upd], runner, log=logs.append)

    assert runner.failures == ["git push"]
    assert any("push failed" in m for m in logs)
    assert not any("pr create" in " ".join(c) for c in run.calls)  # never attempted


# --- thin I/O wrappers ------------------------------------------------------ #

def test_api_get_parses_json():
    run = FakeRun({"curl": (0, '{"tag_name": "v1.0.0"}', "")})
    assert uf.api_get("https://api/x", "tok", run=run) == {"tag_name": "v1.0.0"}


def test_api_get_returns_none_on_curl_failure():
    run = FakeRun({"curl": (22, "", "404")})
    assert uf.api_get("https://api/x", "tok", run=run) is None


def test_api_get_returns_none_on_non_json_body():
    # HTTP 200 but a proxy/rate-limit HTML page instead of JSON.
    run = FakeRun({"curl": (0, "<html>rate limited</html>", "")})
    assert uf.api_get("https://api/x", "tok", run=run) is None


def test_sha256_of_url_extracts_digest():
    run = FakeRun({"sha256sum": (0, "deadbeef  -\n", "")})
    assert uf.sha256_of_url("https://x/a.tar.gz", run=run) == "deadbeef"


def test_sha256_of_url_returns_none_on_empty():
    run = FakeRun({"sha256sum": (0, "", "")})
    assert uf.sha256_of_url("https://x/a.tar.gz", run=run) is None


def test_sha256_of_url_returns_none_on_download_failure():
    # curl -f + pipefail: a 404 fails the pipeline, so no bogus hash is returned.
    run = FakeRun({"sha256sum": (22, "", "curl: (22) 404")})
    assert uf.sha256_of_url("https://x/missing.tar.gz", run=run) is None
