if [[ $PWD =~ "immortalwrt" ]]; then
    PROJECT_NAME="immortalwrt"
    sudo chown -R $(whoami):$(whoami) bin
else
    PROJECT_NAME="openwrt"
fi

PACKAGES_ARCH=$(cat .config | grep CONFIG_TARGET_ARCH_PACKAGES | awk -F '=' '{print $2}' | sed 's/"//g')
OPENWRT_VERSION=$(cat ./include/version.mk | grep 'VERSION_NUMBER:=$(if' | awk -F ',' '{print $3}' | awk -F ')' '{print $1}')
BIG_VERSION=$(echo $OPENWRT_VERSION | awk -F '.' '{print $1"."$2}')
ALL_SUPPORTED=$(curl -ks https://downloads.openwrt.org/releases/ | grep -e "<tr.*/$1" | grep -o 'href="[0-9].*/"' | sed 's/href="//' | sed 's/\/"//' | awk '{print $1}')

# PACKAGES_ARCH: x86_64 OPENWRT_VERSION: 23.05.2 BIG_VERSION: 23.05
echo "PACKAGES_ARCH: $PACKAGES_ARCH OPENWRT_VERSION: $OPENWRT_VERSION BIG_VERSION: $BIG_VERSION"
DISTRIB_ARCH=$PACKAGES_ARCH
DISTRIB_RELEASE=$OPENWRT_VERSION
add_packages() {
    echo "try add $1"

    echo "All supported version: "
    echo "$ALL_SUPPORTED"

    version=$(echo "$DISTRIB_RELEASE" | awk -F- '{print $1}')
    echo "Current version: $version"

    supported=$(echo "$ALL_SUPPORTED" | grep "$version")
    feed_version="$DISTRIB_RELEASE"

    echo "Supported version: "
    echo "$supported"

    if [ -z "$supported" ]; then
        echo "Your device is not supported"
        exit 1
    fi

    FEED_CONF="src/gz brainiac https://cdn.jsdelivr.net/gh/fangguangyang/openwrt-dist@packages/$PACKAGES_ARCH"
    mkdir -p files/etc/opkg/
    echo "$FEED_CONF" >> files/etc/opkg/customfeeds.conf
    # 添加软件源到第一行
    echo "$FEED_CONF" | cat - ./repositories.conf > temp && mv temp ./repositories.conf
}

add_geodata() {
    FEED_URL="src/gz ekkog_geodata https://ghproxy.imciel.com/https://downloads.sourceforge.net/project/ekko-openwrt-dist/$1" 
    echo "$FEED_URL" | cat - ./repositories.conf > temp && mv temp ./repositories.conf
    mkdir -p files/etc/opkg/
    echo "$FEED_URL" >> files/etc/opkg/customfeeds.conf
}
