class Openstash < Formula
  desc "Cache OpenAPI specs locally for fast endpoint lookup"
  homepage "https://github.com/MiguelAPerez/openstash"
  version "0.7.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_arm64.tar.gz"
      sha256 "4c4232905e7a0f6ab666b18a98c0deed22e052394471a9441df545cce132eca7"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_darwin_amd64.tar.gz"
      sha256 "d98dd1039c82d192d169f937de8a177c0cc2131351db5ccf209c1e116847f5d9"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_arm64.tar.gz"
      sha256 "3d87331195933ca087caa7b6977c89f69bd963fcf2961c997a81821e62f83c2d"
    end

    on_intel do
      url "https://github.com/MiguelAPerez/openstash/releases/download/v#{version}/openstash_linux_amd64.tar.gz"
      sha256 "3027350a8e271776e58cada1e1889474d838eadf920b670d108e1c87b58071c6"
    end
  end

  def install
    bin.install "openstash"
  end

  test do
    system "#{bin}/openstash", "--version"
  end
end
