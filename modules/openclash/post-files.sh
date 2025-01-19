mkdir -p files/etc/openclash/config
wget --user-agent='clash' $CLASH_CONFIG_URL -O files/etc/openclash/config/config.yaml
# 下载核心文件
mkdir -p files/etc/openclash/core
wget https://github.com/vernesong/OpenClash/raw/core/master/dev/clash-linux-amd64.tar.gz -O dev.tar.gz
tar -xzf dev.tar.gz
mv clash files/etc/openclash/core/

. ./modules/add-feed-base/base.sh
add_packages "mihomo"
