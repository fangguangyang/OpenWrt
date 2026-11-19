import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('prepare_openclash', Path(__file__).resolve().parents[1] / 'scripts/prepare-openclash.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoreTests(unittest.TestCase):
    def archive(self, binary, name='clash', kind=tarfile.REGTYPE):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(binary) if kind == tarfile.REGTYPE else 0
            archive.addfile(info, io.BytesIO(binary) if kind == tarfile.REGTYPE else None)
        return output.getvalue()

    def test_foreign_architecture_and_non_elf_executables_are_rejected(self):
        binary = bytearray(64)
        binary[:6] = b'\x7fELF\x02\x01'
        binary[18:20] = (183).to_bytes(2, 'little')
        self.assertEqual(module.unpack(self.archive(binary), 183), bytes(binary))
        for data in [self.archive(binary), self.archive(b'not an executable')]:
            with self.assertRaisesRegex(ValueError, 'ELF'):
                module.unpack(data, 62)

    def test_path_traversal_and_symlink_payloads_are_not_extracted(self):
        for name, kind in [('../clash', tarfile.REGTYPE), ('clash', tarfile.SYMTYPE)]:
            with self.subTest(name=name, kind=kind), self.assertRaisesRegex(ValueError, 'regular'):
                module.unpack(self.archive(b'payload', name, kind), 183)


if __name__ == '__main__':
    unittest.main()
