latest_ver=$(curl -s -I https://github.com/AdguardTeam/AdGuardHome/releases/latest | awk -F '/' '/^location/ {print substr($NF, 1, length($NF)-1)}')
wget https://github.com/AdguardTeam/AdGuardHome/releases/download/${latest_ver}/AdGuardHome_linux_amd64.tar.gz
tar -xzf AdGuardHome_linux_amd64.tar.gz
mkdir -p files/usr/bin/
mv AdGuardHome/AdGuardHome files/usr/bin/AdGuardHome
chmod a+x files/usr/bin/AdGuardHome
if [ -n $ADH_PASSWD ]; then
    sed -i "s/\(password:\).*/\1 $ADH_PASSWD/" /etc/adguardhome.yaml
fi