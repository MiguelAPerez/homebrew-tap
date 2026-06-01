class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.1.2"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "402983482e6d6b75e40f05f796f181aa7f0b990e4607d5e224d733c9674b4bca"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "7947c9edfb51da7c64ce478e0957c78627aea66557157491f7c090964b16ae26"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_arm64.tar.gz"
      sha256 "142cadd3fb55f61818293669c79200c2c85dd55a106579a56cb0335a94993528"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_amd64.tar.gz"
      sha256 "b36e51bdf31bb4bbfe407343fbb6d9c9e9601cbcc1df2a5aa0dc833279f14cff"
    end
  end

  def install
    bin.install "openstash"
  end

  test do
    system "#{bin}/openstash", "--version"
  end
end
