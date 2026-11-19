#!/usr/bin/env python3
"""Resolve official release metadata and reuse matching published package feeds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

DEVICES = {
    "amd64": ("x86/64", "generic"),
    "m28c": ("rockchip/armv8", "widora_mangopi-m28c"),
}


def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "OpenWrt-build"}), timeout=60) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def resolve_version(base, requested):
    requested = requested.strip().removeprefix("v")
    if requested.lower() in {"snapshot", "snapshots", "main", "master"}:
        return "SNAPSHOT"
    if requested.lower() in {"", "latest", "stable"}:
        # The first release link is the currently recommended stable release.
        page = fetch(base + "/").decode()
        match = re.search(r'href=[\"\'](?:\./)?releases/(\d+\.\d+\.\d+)/', page)
        if not match:
            raise ValueError("Cannot find the current stable release on " + base)
        return match[1]
    series = re.fullmatch(r"(?:openwrt-)?(\d+\.\d+)", requested)
    if series:
        page = fetch(base + "/releases/").decode()
        versions = set(re.findall(r'href=[\"\'](?:\./)?(' + re.escape(series[1]) + r'\.\d+)/', page))
        if not versions:
            raise ValueError("No stable release for series " + series[1])
        return max(versions, key=lambda v: tuple(map(int, v.split("."))))
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\d+)?", requested):
        raise ValueError("OPENWRT_VERSION must be latest, SNAPSHOT, a series, or a release number")
    return requested


def checksums(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line)
        if match:
            result[match[2].removeprefix("./")] = match[1].lower()
    return result


def archive(sums, distro, kind):
    candidates = [name for name in sums if "/" not in name
                  and name.startswith(f"{distro}-{kind}-")
                  and re.search(r"\.Linux-x86_64\.tar\.(?:zst|xz)$", name)]
    if len(candidates) != 1:
        raise ValueError(f"Expected one {kind} archive, found {candidates}")
    return {"name": candidates[0], "sha256": sums[candidates[0]]}


def resolve(distro, requested, devices):
    base = f"https://downloads.{distro}.org"
    version = resolve_version(base, requested)
    release_path = "snapshots" if version == "SNAPSHOT" else f"releases/{version}"
    matrix = []
    for device in devices:
        if device not in DEVICES:
            raise ValueError("Unknown device: " + device)
        target, profile = DEVICES[device]
        directory = f"{base}/{release_path}/targets/{target}/"
        profiles = json.loads(fetch(directory + "profiles.json"))
        if profile not in profiles["profiles"]:
            raise ValueError(f"{distro} {version} has no {profile} profile; M28C requires ImmortalWrt")
        if not any(p.startswith("apk-") for p in profiles["default_packages"]):
            raise ValueError(f"{distro} {version} {target} does not use APK. Select an APK release.")
        sums = checksums(fetch(directory + "sha256sums").decode())
        branch = ("master" if distro == "immortalwrt" else "main") if version == "SNAPSHOT" else "openwrt-" + ".".join(version.split(".")[:2])
        matrix.append({
            "id": device, "distro": distro, "version": version, "target": target,
            "profile": profile, "arch": profiles["arch_packages"], "package_manager": "apk",
            "source_branch": branch, "directory": directory,
            "sdk": archive(sums, distro, "sdk"),
            "imagebuilder": archive(sums, distro, "imagebuilder"),
            "version_code": profiles.get("version_code", ""),
            "source_date_epoch": profiles.get("source_date_epoch", 0),
        })
    return {"version": version, "include": matrix}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_feed_url(metadata, repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid package repository: " + repository)
    parts = [metadata["distro"], metadata["version"], metadata["target"].replace("/", "-")]
    if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part) for part in parts):
        raise ValueError("Invalid package release tag components")
    return f"https://github.com/{repository}/releases/download/packages-" + "-".join(parts)


def validate_feed(expected, actual, feed_url):
    if expected.get("package_manager") != "apk":
        raise ValueError("Firmware builds require APK metadata")
    if actual.get("feed_url") != feed_url:
        raise ValueError("Package feed metadata does not match its Release URL")
    for key in ("distro", "version", "target", "arch", "package_manager", "version_code"):
        if actual.get(key) != expected[key]:
            raise ValueError(f"Package feed mismatch for {key}: {actual.get(key)} != {expected[key]}")
    if actual.get("sdk", {}).get("sha256") != expected["sdk"]["sha256"]:
        raise ValueError("Package feed was built with a different official SDK")


def check_asset(url):
    with urlopen(Request(url, method="HEAD", headers={"User-Agent": "OpenWrt-build"}), timeout=30) as response:
        if response.headers.get("Content-Length") == "0":
            raise ValueError("Empty published feed asset: " + url)


def resolve_feeds(matrix, repository):
    result = {}
    for metadata in matrix["include"]:
        if metadata.get("package_manager") != "apk":
            raise ValueError("Firmware builds require APK metadata")
        url = package_feed_url(metadata, repository)
        try:
            actual = json.loads(fetch(url + "/build.json"))
            validate_feed(metadata, actual, url)
            for name in ("packages.adb", "feed-key.pem"):
                check_asset(url + "/" + name)
        except HTTPError as error:
            if error.code == 404:
                raise ValueError(f"No complete published package feed for {metadata['id']}: {url}. "
                                 f"Run the Packages workflow in {repository} for this version first; "
                                 "firmware builds do not trigger package builds.") from error
            raise ValueError(f"Cannot read published package feed {url}: HTTP {error.code}") from error
        result[metadata["id"]] = url
    if not result:
        raise ValueError("No devices to resolve package feeds for")
    return result


def download(metadata, kind, destination):
    item = metadata[kind]
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / item["name"]
    if not path.exists() or sha256(path) != item["sha256"]:
        url = urljoin(metadata["directory"], item["name"])
        # Keep large SDK downloads out of memory.
        temporary = path.with_suffix(path.suffix + ".part")
        for attempt in range(4):
            try:
                with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                if sha256(temporary) != item["sha256"]:
                    raise ValueError("SHA256 mismatch for " + url)
                temporary.replace(path)
                break
            except (HTTPError, URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
    return path.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    matrix = sub.add_parser("resolve")
    matrix.add_argument("--distro", choices=["immortalwrt", "openwrt"], default="immortalwrt")
    matrix.add_argument("--version", default=os.getenv("OPENWRT_VERSION", "latest"))
    matrix.add_argument("--devices", default="amd64,m28c")
    matrix.add_argument("--output", type=Path, required=True)
    get = sub.add_parser("download")
    get.add_argument("--metadata", type=Path, required=True)
    get.add_argument("--kind", choices=["sdk", "imagebuilder"], required=True)
    get.add_argument("--directory", type=Path, required=True)
    feeds = sub.add_parser("feeds", help="Find existing matching package Releases without building packages")
    feeds.add_argument("--metadata", type=Path, required=True)
    feeds.add_argument("--repository", default="fangguangyang/openwrt-dist")
    feeds.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "download":
        print(download(json.loads(args.metadata.read_text()), args.kind, args.directory))
        return
    if args.command == "feeds":
        repositories = resolve_feeds(json.loads(args.metadata.read_text()), args.repository)
        args.output.write_text(json.dumps(repositories, indent=2) + "\n")
        if output := os.getenv("GITHUB_OUTPUT"):
            with open(output, "a") as stream:
                stream.write("repositories=" + json.dumps(repositories, separators=(",", ":")) + "\n")
        print(json.dumps(repositories, indent=2))
        return
    result = resolve(args.distro, args.version, [d.strip() for d in args.devices.split(",") if d.strip()])
    if not result["include"]:
        raise ValueError("At least one device is required")
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if output := os.getenv("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            stream.write("version=" + result["version"] + "\n")
            stream.write("matrix=" + json.dumps({"include": result["include"]}, separators=(",", ":")) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, HTTPError, URLError) as error:
        sys.exit(str(error))
