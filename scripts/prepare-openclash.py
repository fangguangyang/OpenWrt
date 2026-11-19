#!/usr/bin/env python3
"""Bundle the OpenClash Meta core for the target CPU, with source provenance."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from release import fetch


# Record both archive hashes together whenever updating the upstream commit.
CORE_COMMIT = '5606dc41ab4bdf11471a6d74e6518a634a2e3e9d'
CORE_ARCHIVES = {
    'amd64': '61ebc9ace8483678a94e3d9ba328415fac1f88864f2b5c4d9bbff0557fc1038f',
    'arm64': 'aae510c46001b8784b1480be94c3c740db9b387e5419604abaafa4189cd99c6d',
}


def unpack(data, machine):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = [member for member in archive.getmembers()
                   if member.name.removeprefix('./') == 'clash' and member.isfile()]
        if len(members) != 1:
            raise ValueError('OpenClash core archive must contain one regular clash executable')
        binary = archive.extractfile(members[0]).read()
    if (len(binary) < 64 or binary[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(binary[18:20], 'little') != machine):
        raise ValueError('OpenClash core ELF does not match the target architecture')
    return binary


def prepare(arch, files, provenance):
    if arch == 'x86_64':
        flavor, machine = 'amd64', 62
    elif arch.startswith('aarch64'):
        flavor, machine = 'arm64', 183
    else:
        raise ValueError('Unsupported OpenClash core architecture: ' + arch)
    url = f'https://raw.githubusercontent.com/vernesong/OpenClash/{CORE_COMMIT}/master/meta/clash-linux-{flavor}.tar.gz'
    data = fetch(url)
    archive_sha256 = hashlib.sha256(data).hexdigest()
    if archive_sha256 != CORE_ARCHIVES[flavor]:
        raise ValueError(f'OpenClash {flavor} core archive SHA256 mismatch at {CORE_COMMIT}')
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    binary = unpack(data, machine)
    destination = files / 'etc/openclash/core/clash_meta'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(binary)
    destination.chmod(0o755)
    provenance.write_text(json.dumps(dict(url=url, commit=CORE_COMMIT, arch=arch, git_blob=blob,
                                          archive_sha256=archive_sha256,
                                          executable_sha256=hashlib.sha256(binary).hexdigest()), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arch')
    parser.add_argument('files', type=Path)
    parser.add_argument('provenance', type=Path)
    args = parser.parse_args()
    prepare(args.arch, args.files, args.provenance)
