latest_ver=$(curl -s -I https://github.com/AdguardTeam/AdGuardHome/releases/latest | awk -F '/' '/^location/ {print substr($NF, 1, length($NF)-1)}')
wget https://github.com/AdguardTeam/AdGuardHome/releases/download/${latest_ver}/AdGuardHome_linux_amd64.tar.gz
tar -xzf AdGuardHome_linux_amd64.tar.gz
ls -lh
ls -lh AdGuardHome/
mv AdGuardHome/AdGuardHome files/usr/bin/AdGuardHome
chmod a+x files/usr/bin/AdGuardHome