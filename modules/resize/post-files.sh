wget -U "" -O temp.sh "https://openwrt.org/_export/code/docs/guide-user/advanced/expand_root?codeblock=0"
sed -E 's|^(cat << "EOF" [>]?>>?) /etc/|\1 /file/etc/|' temp.sh > expand-root.sh
. ./expand-root.sh