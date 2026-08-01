class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.5.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "7d0015807ef7135dcdb69f45ef5e3efea6314e46b42afc8462e44621ced3203b"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "e8c9a89a77474d1bb45c419bc3a2dc59ce37b38825e42281d5e69cc997a348e7"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_arm64.tar.gz"
      sha256 "36e0c35f24e744cb35080ef2271a67276f0a08012e6e2fa2be1cc6eb08fea3ad"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_amd64.tar.gz"
      sha256 "4bec52ac23dab8086a6dc8b563b41e4b460d1892b0921c340b2e3dd700952289"
    end
  end

  def install
    bin.install "openstash"
  end

  test do
    system "#{bin}/openstash", "--version"
  end
end
