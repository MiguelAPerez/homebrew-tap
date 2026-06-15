class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.4.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "13cbba4acd7ae3e2ee091d1cb49acc5ffe52a9f6d028c4951de371eb0bf64f95"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "59a1586827c3b2ee44104b37a7e1cf95be9c7e5bd771151dc2293df79f1f432c"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_arm64.tar.gz"
      sha256 "7611702bc5061144b3eab3b9506c0027df99c27d935bab05711ab3541f7b04bc"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_amd64.tar.gz"
      sha256 "dfe4127fb32518fa854598e50a99498e090d261c22a8b30de7f6f9f00bd89ec8"
    end
  end

  def install
    bin.install "openstash"
  end

  test do
    system "#{bin}/openstash", "--version"
  end
end
