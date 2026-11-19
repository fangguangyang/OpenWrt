#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
metadata=$(realpath "${1:?Usage: build-image.sh metadata.json feed-release-url}")
feed_url=${2:?A fixed GitHub Release feed URL is required}
feed_url=${feed_url%/}
if [[ ! $feed_url =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[A-Za-z0-9_.-]+$ ]]; then
    echo 'Expected https://github.com/OWNER/REPO/releases/download/TAG' >&2
    exit 1
fi
mapfile -t fields < <(python3 - "$metadata" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
for key in ('id', 'target', 'profile', 'package_manager', 'arch'):
    print(m[key])
PY
)
device=${fields[0]}
target=${fields[1]}
profile=${fields[2]}
manager=${fields[3]}
arch=${fields[4]}
if [[ $manager != apk ]]; then
    echo 'Firmware builds require APK metadata' >&2
    exit 1
fi
if [[ $device != amd64 && $device != m28c ]]; then
    echo "Unknown device: $device" >&2
    exit 1
fi

read_list() {
    awk '{sub(/#.*/, ""); for (i = 1; i <= NF; i++) if (!seen[$i]++) print $i}' "$@"
}

device_profile="$root/profiles/$device"
requested_features=$(read_list "$device_profile/features")
feature_profiles=()
package_lists=("$root/profiles/common.packages" "$device_profile/packages")
while IFS= read -r feature; do
    [[ -n $feature ]] || continue
    feature_profile="$root/profiles/features/$feature"
    if [[ ! $feature =~ ^[a-z0-9-]+$ || ! -d $feature_profile ]]; then
        echo "Unknown firmware feature '$feature' in profiles/$device/features" >&2
        exit 1
    fi
    feature_profiles+=("$feature_profile")
    if [[ -f $feature_profile/packages ]]; then
        package_lists+=("$feature_profile/packages")
    fi
done <<< "$requested_features"
work=${BUILD_WORKDIR:-"$root/.build/$device"}
mkdir -p "$work" "$work/downloads" "$root/image/$device"
work=$(realpath "$work")
curl -fsSL --retry 3 "$feed_url/build.json" -o "$work/feed.json"
python3 - "$root/scripts" "$metadata" "$work/feed.json" "$feed_url" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
from release import validate_feed
expected, actual = [json.load(open(p)) for p in sys.argv[2:4]]
validate_feed(expected, actual, sys.argv[4])
PY
archive=$(python3 "$root/scripts/release.py" download --metadata "$metadata" --kind imagebuilder --directory "$work/downloads")
# A fresh builder prevents stale image formats, FILES overrides and duplicate
# repositories from leaking into a second local build in the same workdir.
builder=$(mktemp -d "$work/builder.XXXXXX")
tar -xf "$archive" --strip-components=1 -C "$builder"
mkdir -p "$work/package-cache"
ln -s "$work/package-cache" "$builder/dl"
cd "$builder"
cp "$work/feed.json" feed.json

mkdir -p files keys
cp -a "$root/profiles/common/files/." files/
for feature_profile in "${feature_profiles[@]}"; do
    if [[ -d $feature_profile/files ]]; then
        cp -a "$feature_profile/files/." files/
    fi
done
cp -a "$device_profile/files/." files/
find files/etc/uci-defaults -type f -exec chmod 755 {} +
for directory in files/etc/init.d files/usr/sbin files/etc/hotplug.d; do
    [[ ! -d $directory ]] || find "$directory" -type f -exec chmod 755 {} +
done
if [[ -f $device_profile/image.config ]]; then
    python3 - "$device_profile/image.config" <<'PY'
from pathlib import Path
import re, sys
config = Path('.config')
text = config.read_text()
for line in Path(sys.argv[1]).read_text().splitlines():
    match = re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=.*|# (CONFIG_[A-Z0-9_]+) is not set', line)
    if match:
        key = match[1] or match[2]
        text = re.sub(r'(?m)^(?:' + key + r'=.*|# ' + key + r' is not set)\n?', '', text)
        text += line + '\n'
config.write_text(text)
PY
fi
mkdir -p files/etc/apk/keys files/etc/apk/repositories.d
curl -fsSL --retry 3 "$feed_url/feed-key.pem" -o keys/custom-feed.pem
cp keys/custom-feed.pem files/etc/apk/keys/
printf '%s/packages.adb\n' "$feed_url" >> repositories
printf '%s/packages.adb\n' "$feed_url" > files/etc/apk/repositories.d/customfeeds.list

packages=$(read_list "${package_lists[@]}")
packages=${packages//$'\n'/ }
options=("PROFILE=$profile" "PACKAGES=$packages" "FILES=$PWD/files" "ROOTFS_PARTSIZE=1024")
options+=("DISABLED_SERVICES=passwall snmpd miniupnpd")
make info
# Real dependency installation catches missing packages, ABI mismatches and
# file conflicts before image generation, and retains the full package list.
make manifest "PROFILE=$profile" "PACKAGES=$packages" > "$root/image/$device/package-manifest.txt"
if [[ $device == m28c ]]; then
    python3 "$root/scripts/prepare-m28c.py" "$PWD"
fi
python3 "$root/scripts/prepare-openclash.py" "$arch" "$PWD/files" "$root/image/$device/openclash-core.json"
make image "${options[@]}"
cp "$metadata" "$root/image/$device/build.json"
cp feed.json "$root/image/$device/feed.json"
printf '%s\n' "$feed_url" > "$root/image/$device/feed-url.txt"
find "bin/targets/$target" -maxdepth 1 -type f -exec cp {} "$root/image/$device/" \;
mkdir -p "$root/release"
tar -czf "$root/release/$device-firmware.tar.gz" -C "$root/image/$device" .
find "$root/image/$device" -maxdepth 1 -name '*.img.gz' -exec cp {} "$root/release/" \;
