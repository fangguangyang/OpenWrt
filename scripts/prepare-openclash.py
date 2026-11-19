#!/usr/bin/env python3
"""Bundle the OpenClash Meta core for the target CPU, with source provenance."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

from release import fetch


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
    api = 'https://api.github.com/repos/vernesong/OpenClash'
    commit = json.loads(fetch(api + '/commits/core'))['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid OpenClash core commit')
    path = f'master/meta/clash-linux-{flavor}.tar.gz'
    entry = json.loads(fetch(f'{api}/contents/{path}?ref={commit}'))
    url = f'https://raw.githubusercontent.com/vernesong/OpenClash/{commit}/{path}'
    data = fetch(url)
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if entry['sha'] != blob or entry['size'] != len(data):
        raise ValueError('OpenClash core archive does not match the pinned Git blob')
    binary = unpack(data, machine)
    destination = files / 'etc/openclash/core/clash_meta'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(binary)
    destination.chmod(0o755)
    provenance.write_text(json.dumps(dict(url=url, commit=commit, arch=arch, git_blob=blob,
                                          archive_sha256=hashlib.sha256(data).hexdigest(),
                                          executable_sha256=hashlib.sha256(binary).hexdigest()), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arch')
    parser.add_argument('files', type=Path)
    parser.add_argument('provenance', type=Path)
    args = parser.parse_args()
    prepare(args.arch, args.files, args.provenance)
