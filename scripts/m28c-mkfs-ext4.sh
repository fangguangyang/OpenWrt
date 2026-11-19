#!/usr/bin/env bash
# Use e2fsprogs for an ext4 root that can be grown by the same tool family.
set -euo pipefail
if [[ ${1:-} != --fakeroot ]]; then
    builder=${1:?builder directory required}
    exec "$builder/staging_dir/host/bin/fakeroot" "$0" --fakeroot "$@"
fi
shift
builder=$1
image=$2
directory=$3
bytes=$4
blocksize=$5
epoch=$6
host="$builder/staging_dir/host/bin"
# Match make_ext4fs's default ownership while retaining permissions/symlinks.
# fakeroot keeps this metadata operation inside the generated image only.
chown -h -R 0:0 "$directory"
export E2FSPROGS_FAKE_TIME=$epoch
export MKE2FS_CONFIG="$builder/tmp/m28c-mke2fs.conf"
cat > "$MKE2FS_CONFIG" <<'CONF'
[defaults]
    base_features = sparse_super,large_file,filetype,resize_inode,dir_index,ext_attr
    inode_ratio = 16384
[fs_types]
    ext4 = {
        features = has_journal,extent,huge_file,dir_nlink,extra_isize,uninit_bg
    }
CONF
"$host/mke2fs" -q -t ext4 -F -L rootfs -m 0 -b "$blocksize" -I 256 -i 16384 \
    -O has_journal,extent,filetype,large_file,huge_file,dir_nlink,extra_isize,uninit_bg,sparse_super,resize_inode \
    -E lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0 \
    -d "$directory" "$image" "$((bytes / blocksize))"
"$host/e2fsck" -fn "$image"
