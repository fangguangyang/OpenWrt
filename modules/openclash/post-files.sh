. ./modules/download-arch/base.sh
mkdir -p files/etc/openclash/config
if [ -n "${CLASH_CONFIG_URL:-}" ]; then
    wget --user-agent='clash' "$CLASH_CONFIG_URL" -O files/etc/openclash/config/config.yaml
fi
# 下载核心文件
mkdir -p files/etc/openclash/core
wget "https://raw.githubusercontent.com/vernesong/OpenClash/core/master/meta/clash-linux-${download_arch}.tar.gz" -O dev.tar.gz
tar -xzf dev.tar.gz
mv clash files/etc/openclash/core/clash_meta

. ./modules/add-feed-base/base.sh
add_packages "mihomo"
