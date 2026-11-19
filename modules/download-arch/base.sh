# Map the target architecture, never the ImageBuilder host's uname.
target_arch=$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES="\(.*\)"/\1/p' .config)
case "$target_arch" in
    x86_64) download_arch=amd64 ;;
    aarch64*) download_arch=arm64 ;;
    *) echo "Unsupported binary download architecture: $target_arch" >&2; exit 1 ;;
esac
