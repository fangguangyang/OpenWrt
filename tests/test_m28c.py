import importlib.util
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'profiles/m28c/files'


class UsbDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sys = self.root / 'sys'
        self.helper = self.root / 'fm350.sh'
        self.helper.write_text((FILES / 'lib/functions/fm350.sh').read_text().replace('/sys/', str(self.sys) + '/'))

    def usb(self, product='7127', interface='06', port='ttyUSB9', net='enx012345', driver='rndis_host'):
        usb = self.sys / 'devices/usb1/1-1'
        usb.mkdir(parents=True, exist_ok=True)
        (usb / 'idVendor').write_text('0e8d\n')
        (usb / 'idProduct').write_text(product + '\n')
        control = usb / ('1-1:1.' + str(int(interface, 16)))
        control.mkdir(exist_ok=True)
        (control / 'bInterfaceNumber').write_text(interface + '\n')
        tty = control / port if port.startswith('ttyUSB') else control
        tty.mkdir(exist_ok=True)
        entry = self.sys / 'class/tty' / port
        entry.mkdir(parents=True)
        (entry / 'device').symlink_to(tty)
        data = usb / '1-1:1.0'
        netdir = data / 'net' / net
        netdir.mkdir(parents=True, exist_ok=True)
        (netdir / 'device').symlink_to(data)
        drv = self.sys / 'bus/usb/drivers' / driver
        drv.mkdir(parents=True, exist_ok=True)
        (data / 'driver').symlink_to(drv)
        return usb

    def detect(self):
        return subprocess.run(['sh', '-c', '. "$1"; fm350_find || exit 1; printf "%s %s" "$FM350_PORT" "$FM350_NET"',
                               'sh', str(self.helper)], text=True, capture_output=True)

    def test_both_usb_products_follow_interface_number_and_not_tty_index(self):
        for product, interface in [('7126', '04'), ('7127', '06')]:
            with self.subTest(product=product):
                shutil.rmtree(self.sys, ignore_errors=True)
                self.usb(product, interface)
                result = self.detect()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '/dev/ttyUSB9 enx012345')

    def test_acm_sysfs_depth_is_supported(self):
        self.usb(port='ttyACM3')
        self.assertEqual(self.detect().stdout, '/dev/ttyACM3 enx012345')

    def test_debug_ports_unknown_models_and_unbound_networks_are_ignored(self):
        for product, interface, driver in [('7127', '04', 'rndis_host'), ('0001', '06', 'rndis_host'),
                                           ('7127', '06', 'unknown')]:
            with self.subTest(product=product, interface=interface, driver=driver):
                shutil.rmtree(self.sys, ignore_errors=True)
                self.usb(product, interface, driver=driver)
                self.assertNotEqual(self.detect().returncode, 0)

    def test_multiple_data_interfaces_are_not_guessed(self):
        usb = self.usb()
        netdir = usb / '1-1:1.0/net/usb1'
        netdir.mkdir()
        (netdir / 'device').symlink_to(usb / '1-1:1.0')
        self.assertNotEqual(self.detect().returncode, 0)


class GrowRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls = self.root / 'calls'
        for name, value in {
            'tmp/sysinfo/board_name': 'widora,mangopi-m28c',
            'proc/self/mountinfo': '18 0 179:2 / / rw - ext4 /dev/root rw\n',
            'sys/class/block/mmcblk1p2/partition': '2',
            'sys/class/block/mmcblk1p2/start': '196608',
            'sys/class/block/mmcblk1p2/size': '2097152',
            'sys/class/block/mmcblk1/size': '125000000',
            'sys/class/block/mmcblk1/device/type': 'SD',
        }.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)
        device = self.root / 'sys/dev/block/179:2'
        device.parent.mkdir(parents=True)
        device.symlink_to(self.root / 'sys/class/block/mmcblk1/mmcblk1p2')
        (self.root / 'etc').mkdir()
        self.table = self.root / 'partition-table'
        self.write_table(2293759)
        self.script = self.root / 'growroot'
        text = (FILES / 'usr/sbin/m28c-growroot').read_text()
        for prefix in ('/tmp/sysinfo/', '/proc/self/', '/sys/dev/', '/sys/class/', '/etc/m28c-', '/tmp/m28c-'):
            text = text.replace(prefix, str(self.root) + prefix)
        self.script.write_text(text)
        self.fake('parted', '''case " $* " in
  *' resizepart '*)
    [ "$RESIZE_FAIL" != 1 ] || exit 1
    if [ "$MOUNTED" = 1 ]; then
      case "$*" in *---pretend-input-tty*) ;; *) exit 1 ;; esac
      read -r answer
      [ "$answer" = Yes ] || exit 1
    fi
    sed -i 's/2293759s:2097152s/124999999s:124803392s/' "$FIXTURE/partition-table"
    ;;
  *) cat "$FIXTURE/partition-table" ;;
esac
''')
        self.fake('resize2fs', '[ "$FS_FAIL" != 1 ]\n')
        self.fake('tune2fs', 'printf "Block count: 15600424\\nBlock size: 4096\\n"\n')
        for name in ('logger', 'reboot', 'sync'):
            self.fake(name, 'exit 0\n')
        self.env = dict(os.environ, FIXTURE=str(self.root), PATH=str(self.bin) + ':' + os.environ['PATH'])

    def fake(self, name, script):
        p = self.bin / name
        p.write_text('#!/bin/sh\nprintf "%s %s\\n" "${0##*/}" "$*" >> "$FIXTURE/calls"\n' + script)
        p.chmod(0o755)

    def write_table(self, end, extra=False):
        self.table.write_text(f'BYT;\n/dev/mmcblk1:125000000s:sd/mmc:512:512:msdos:SD:;\n'
                              f'1:65536s:196607s:131072s:ext4::;\n2:196608s:{end}s:{end - 196607}s:ext4::;\n'
                              + ('3:2300000s:124999999s:122700000s:ext4::;\n' if extra else ''))

    def run_script(self, **env):
        result = subprocess.run(['sh', str(self.script)], env=dict(self.env, **env), capture_output=True, text=True)
        self.assertEqual(result.stderr, '', result.stderr)
        return result

    def call_text(self):
        return self.calls.read_text() if self.calls.exists() else ''

    def grown_partition(self):
        self.write_table(124999999)
        (self.root / 'sys/class/block/mmcblk1p2/size').write_text('124803392')

    def test_partition_grows_then_reboots_once_and_ext4_grows_on_next_boot(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn('parted ---pretend-input-tty /dev/mmcblk1 resizepart 2 100%', self.call_text())
        self.assertIn('reboot ', self.call_text())
        self.assertNotIn('resize2fs ', self.call_text())
        self.grown_partition()
        self.calls.write_text('')
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn('resize2fs /dev/mmcblk1p2', self.call_text())
        self.assertNotIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])
        self.assertTrue((self.root / 'etc/m28c-growroot.done').exists())
        self.calls.write_text('')
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.call_text(), '')

    def test_trailing_data_partition_is_never_overwritten(self):
        self.write_table(2293759, extra=True)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn('resizepart', self.call_text())
        self.assertNotIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])

    def test_mounted_root_confirmation_is_supplied_before_partition_growth(self):
        self.assertEqual(self.run_script(MOUNTED='1').returncode, 0)
        self.assertIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])

    def test_failed_partition_resize_does_not_reboot(self):
        self.assertNotEqual(self.run_script(RESIZE_FAIL='1').returncode, 0)
        self.assertNotIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])
        self.assertFalse((self.root / 'etc/m28c-growroot.done').exists())

    def test_pending_marker_prevents_reboot_loop_if_partition_write_did_not_persist(self):
        (self.root / 'etc/m28c-growroot.pending').write_text('mmcblk1:196608:125000000')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn('resizepart', self.call_text())
        self.assertNotIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])

    def test_stale_kernel_partition_size_is_not_used_to_resize_ext4(self):
        self.write_table(124999999)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn('resize2fs ', self.call_text())

    def test_filesystem_resize_failure_is_retried_without_marking_success(self):
        self.grown_partition()
        self.assertNotEqual(self.run_script(FS_FAIL='1').returncode, 0)
        self.assertFalse((self.root / 'etc/m28c-growroot.done').exists())
        self.assertNotIn('reboot', [line.split(' ', 1)[0] for line in self.call_text().splitlines()])
        self.assertEqual(self.run_script().returncode, 0)

    def test_emmc_and_squashfs_are_not_modified(self):
        (self.root / 'sys/class/block/mmcblk1/device/type').write_text('MMC')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn('parted ', self.call_text())
        (self.root / 'sys/class/block/mmcblk1/device/type').write_text('SD')
        (self.root / 'proc/self/mountinfo').write_text('18 0 0:18 / / rw - overlay overlay rw\n')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertNotIn('parted ', self.call_text())


class ProtocolPatchTests(unittest.TestCase):
    def test_upstream_drift_fails_instead_of_emitting_an_unpatched_firmware(self):
        spec = importlib.util.spec_from_file_location('prepare_m28c', ROOT / 'scripts/prepare-m28c.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = root / 'build_dir/target-test/root-rockchip/lib/netifd/proto/xmm.sh'
            protocol.parent.mkdir(parents=True)
            protocol.write_text('new upstream implementation\n')
            with self.assertRaisesRegex(ValueError, 'changed upstream'):
                module.prepare(root, root / 'files')
            self.assertFalse((root / 'files').exists())


if __name__ == '__main__':
    unittest.main()
