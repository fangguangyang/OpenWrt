if [[ $PWD =~ "immortalwrt" ]]; then
    PROJECT_NAME="immortalwrt"
    sudo chown -R $(whoami):$(whoami) bin
else
    PROJECT_NAME="openwrt"
fi

PACKAGES_ARCH=$(cat .config | grep CONFIG_TARGET_ARCH_PACKAGES | awk -F '=' '{print $2}' | sed 's/"//g')
OPENWRT_VERSION=$(cat ./include/version.mk | grep 'VERSION_NUMBER:=$(if' | awk -F ',' '{print $3}' | awk -F ')' '{print $1}')
BIG_VERSION=$(echo $OPENWRT_VERSION | awk -F '.' '{print $1"."$2}')

# PACKAGES_ARCH: x86_64 OPENWRT_VERSION: 23.05.2 BIG_VERSION: 23.05
echo "PACKAGES_ARCH: $PACKAGES_ARCH OPENWRT_VERSION: $OPENWRT_VERSION BIG_VERSION: $BIG_VERSION"
DISTRIB_ARCH=$PACKAGES_ARCH
DISTRIB_RELEASE=$OPENWRT_VERSION
add_packages() {
    echo "try add $1"

    # | awk '{printf "%s ", $0} END {print ""}')
    all_supported=$(curl -ks https://downloads.openwrt.org/releases/ | grep -e "<tr.*/$1" | grep -o 'href="[0-9].*/"' | sed 's/href="//' | sed 's/\/"//')

    echo "All supported version: "
    echo "$all_supported"

    version=$(echo "$DISTRIB_RELEASE" | awk -F- '{print $1}')
    echo "Current version: $version"

    # get the first two version number
    big_version=$(echo "$version" | awk -F. '{print $1"."$2}')

    if [ "$1" == "luci" ]; then
        supported=$(echo "$all_supported" | grep "$big_version")
        feed_version="$DISTRIB_RELEASE"
    else
        supported=$(echo "$all_supported" | grep $DISTRIB_ARCH | grep $big_version)
        feed_version="$DISTRIB_ARCH-v$DISTRIB_RELEASE"
    fi

    echo "Supported version: "
    echo "$supported"

    if [ -z "$supported" ]; then
        echo "Your device is not supported"
        exit 1
    fi

    full_support=0
    for i in $supported; do
        if [ "$i" = "$feed_version" ]; then
            full_support=1
            break
        fi
    done

    if [ "$full_support" = "0" ]; then
        echo "Your device is not fully supported"
        echo "Find the latest version that supports your device"

        # 过滤掉 rc 和 SNAPSHOT 版本, 不用 grep
        final_release=$(echo "$supported" | grep -v "\-rc" | grep -v "SNAPSHOT" | tail -n 1)
        if [ -z "$final_release" ]; then
            echo "No final release found, use the latest rc version"
            feed_version=$(echo "$supported" | grep "\-rc" | tail -n 1)
        else
            feed_version=$final_release
        fi
    fi
    echo "Feed version: $feed_version"
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
