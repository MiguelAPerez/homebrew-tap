class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.3.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "cefab8b45a56969490602d8a1738e7580be3cc1a7f66ee176a9f54a7d849e83a"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "f8b3f0ba911c48d7b1707d38b19ad43e09b74b86dd54af996da432cec14a28dc"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_arm64.tar.gz"
      sha256 "2682d3e64a7106264507a00d5ba66b23e0105db30e00c0284f68953b3d68f0eb"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_amd64.tar.gz"
      sha256 "2202f5d366eabb522e6fac496c2733020093c5b0efe8346b9c697d6ce1ee20f3"
    end
  end

  def install
    bin.install "openstash"
  end

  test do
    system "#{bin}/openstash", "--version"
  end
end
