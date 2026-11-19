. ./modules/download-arch/base.sh
latest_ver=$(curl -fsSL --retry 3 https://api.github.com/repos/AdguardTeam/AdGuardHome/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
wget "https://github.com/AdguardTeam/AdGuardHome/releases/download/${latest_ver}/AdGuardHome_linux_${download_arch}.tar.gz"
tar -xzf "AdGuardHome_linux_${download_arch}.tar.gz"
mkdir -p files/usr/bin/
mv AdGuardHome/AdGuardHome files/usr/bin/AdGuardHome
chmod a+x files/usr/bin/AdGuardHome
