cp files/etc/opkg/keys/* 
wget https://cdn.jsdelivr.net/gh/fangguangyang/openwrt-dist@master/brainiac-dist.pub
opkg-key add brainiac-dist.pub