#!/usr/bin/env python3
"""Prepare FM350 USB discovery and a growable M28C ext4 root filesystem."""
import argparse
from pathlib import Path
import re
import shutil


ANCHOR = '\t[ -z $ifname ] && {\n'
DISCOVERY = '''\t# M28C: select the data interface belonging to this FM350 AT port.
\t# Upstream otherwise requires a fixed MAC and assumes ttyUSB sysfs depth.
\t. /lib/functions/fm350.sh
\tif fm350_for_port "$device"; then
\t\tPREFIX="fm350"
\t\tXMMDNS="GTDNS"
\t\tAUTHCMD="CGAUTH"
\t\tDNSQUERY="GTDNS=$profile"
\t\tifname="$FM350_NET"
\tfi
'''


def prepare(builder, files):
    candidates = list(builder.glob('build_dir/target-*/root-*/lib/netifd/proto/xmm.sh'))
    if len(candidates) != 1:
        raise ValueError(f'Expected one installed xmm-modem protocol, found {candidates}')
    text = candidates[0].read_text()
    if text.count(ANCHOR) != 1 or '0e8d7126|0e8d7127)' not in text:
        raise ValueError('xmm-modem discovery changed upstream; review the M28C compatibility patch')
    destination = files / 'lib/netifd/proto/xmm.sh'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text.replace(ANCHOR, DISCOVERY + ANCHOR))
    destination.chmod(0o755)
    # make_ext4fs emits bitmap padding and resize-inode metadata that do not
    # survive a large growth cleanly with e2fsprogs. Generate this SD root with
    # the ImageBuilder's own e2fsprogs, then check it before packaging.
    image_mk = builder / 'include/image.mk'
    recipe = '''define Image/mkfs/ext4
\t$(TOPDIR)/scripts/m28c-mkfs-ext4.sh "$(TOPDIR)" "$@" \\
\t\t"$(call mkfs_target_dir,$(1))/" "$(ROOTFS_PARTSIZE)" \\
\t\t"$(CONFIG_TARGET_EXT4_BLOCKSIZE)" "$(SOURCE_DATE_EPOCH)"
endef'''
    text, count = re.subn(r'(?ms)^define Image/mkfs/ext4\n.*?^endef', lambda _: recipe, image_mk.read_text())
    if count != 1:
        raise ValueError('Expected one ext4 image recipe in the official ImageBuilder')
    image_mk.write_text(text)
    script = builder / 'scripts/m28c-mkfs-ext4.sh'
    shutil.copy2(Path(__file__).with_name('m28c-mkfs-ext4.sh'), script)
    script.chmod(0o755)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('builder', type=Path)
    parser.add_argument('files', type=Path)
    args = parser.parse_args()
    prepare(args.builder, args.files)
