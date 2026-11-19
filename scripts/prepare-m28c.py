#!/usr/bin/env python3
"""Verify QModem support and prepare the M28C ext4 SD image."""
import argparse
import json
from pathlib import Path
import re
import shutil


def verify_qmodem(builder):
    tables = list(builder.glob('build_dir/target-*/root-*/usr/share/qmodem/modem_support.json'))
    if len(tables) != 1:
        raise ValueError('Expected one installed QModem modem support table')
    table = tables[0]
    root = table.parents[3]
    for name in ('usr/share/luci/menu.d/luci-app-qmodem-next.json', 'etc/config/qmodem', 'usr/bin/modem_scand',
                 'etc/init.d/qmodem_init', 'etc/init.d/qmodem_network'):
        if not (root / name).is_file():
            raise ValueError(f'Missing QModem component: {name}')
    support = json.loads(table.read_text())['modem_support']
    modem = support['usb']['fm350-gl']
    ids = support['device']['fibocom']['mediatek']
    if ('rndis' not in modem['modes'] or modem['pdp_index'] != '0' or
            '0e8d' not in ids['vendor_id'] or not {'7126', '7127'} <= set(ids['product_id'])):
        raise ValueError('QModem FM350-GL USB support differs from the expected RNDIS profile')


def prepare(builder):
    verify_qmodem(builder)
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
    args = parser.parse_args()
    prepare(args.builder)
