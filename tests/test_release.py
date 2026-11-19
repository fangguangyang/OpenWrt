import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_latest_and_series_ignore_release_candidates(self):
        with patch.object(release, "fetch", return_value=b'<a href="releases/25.12.2/targets/">stable</a><a href="releases/24.10.6/targets/">old</a>'):
            self.assertEqual(release.resolve_version("https://example.org", "latest"), "25.12.2")
        with patch.object(release, "fetch", return_value=b'<a href="25.12.9/">9</a><a href="25.12.10/">10</a><a href="25.12.11-rc1/">rc</a>'):
            self.assertEqual(release.resolve_version("https://example.org", "openwrt-25.12"), "25.12.10")

    def test_matrix_uses_metadata_and_both_archive_formats(self):
        def fetch(url):
            if url.endswith("profiles.json"):
                return json.dumps({"profiles": {"generic": {}, "widora_mangopi-m28c": {}},
                                   "default_packages": ["apk-openssl"], "arch_packages": "aarch64_generic"}).encode()
            return (("a" * 64 + " *immortalwrt-sdk-25.12.2-test_gcc-99.Linux-x86_64.tar.zst\n") +
                    ("b" * 64 + "  immortalwrt-imagebuilder-25.12.2-test.Linux-x86_64.tar.xz\n")).encode()
        with patch.object(release, "fetch", side_effect=fetch):
            result = release.resolve("immortalwrt", "25.12.2", ["amd64", "m28c"])
        self.assertEqual([item["target"] for item in result["include"]], ["x86/64", "rockchip/armv8"])
        self.assertEqual(result["include"][1]["package_manager"], "apk")
        self.assertEqual(result["include"][1]["profile"], "widora_mangopi-m28c")

    def test_missing_device_profile_fails(self):
        with patch.object(release, "fetch", return_value=b'{"profiles":{"generic":{}}}'):
            with self.assertRaisesRegex(ValueError, "M28C requires ImmortalWrt"):
                release.resolve("openwrt", "25.12.6", ["m28c"])

    def test_release_without_apk_is_rejected_before_fetching_checksums(self):
        profiles = b'{"profiles":{"generic":{}},"default_packages":["opkg"]}'
        with patch.object(release, "fetch", return_value=profiles) as fetch:
            with self.assertRaisesRegex(ValueError, "does not use APK"):
                release.resolve("immortalwrt", "24.10.6", ["amd64"])
        fetch.assert_called_once()

    def test_snapshot_aliases_and_invalid_versions(self):
        for alias in ("SNAPSHOT", "main", "master"):
            self.assertEqual(release.resolve_version("https://example.org", alias), "SNAPSHOT")
        with self.assertRaises(ValueError):
            release.resolve_version("https://example.org", "$(invalid)")

    def test_corrupt_download_is_rejected(self):
        metadata = {"directory": "https://example.org/", "sdk": {"name": "sdk.tar.zst", "sha256": hashlib.sha256(b"valid").hexdigest()}}
        with tempfile.TemporaryDirectory() as directory, patch.object(release, "urlopen", return_value=io.BytesIO(b"corrupt")):
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                release.download(metadata, "sdk", Path(directory))
            self.assertFalse((Path(directory) / "sdk.tar.zst").exists())


class PublishedFeedTests(unittest.TestCase):
    def metadata(self, **changes):
        return dict({"id": "amd64", "distro": "immortalwrt", "version": "25.12.2",
                     "target": "x86/64", "profile": "generic", "arch": "x86_64", "package_manager": "apk",
                     "version_code": "r123-abc", "sdk": {"sha256": "a" * 64}}, **changes)

    def published(self, metadata):
        url = release.package_feed_url(metadata, "fangguangyang/openwrt-dist")
        return dict(metadata, feed_url=url)

    def test_reuses_exact_existing_release_for_each_device_without_downloads(self):
        targets = [self.metadata(), self.metadata(id="m28c", target="rockchip/armv8", arch="aarch64_generic")]
        published = {self.published(item)["feed_url"] + "/build.json": json.dumps(self.published(item)).encode() for item in targets}
        with patch.object(release, "fetch", side_effect=published.__getitem__) as fetch, \
             patch.object(release, "check_asset") as check, patch.object(release, "download") as download:
            result = release.resolve_feeds({"include": targets}, "fangguangyang/openwrt-dist")
        self.assertEqual(result["amd64"], "https://github.com/fangguangyang/openwrt-dist/releases/download/packages-immortalwrt-25.12.2-x86-64")
        self.assertTrue(result["m28c"].endswith("packages-immortalwrt-25.12.2-rockchip-armv8"))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(check.call_count, 4)
        download.assert_not_called()

    def test_metadata_mismatch_is_rejected_instead_of_selecting_another_release(self):
        expected = self.metadata()
        url = self.published(expected)["feed_url"]
        for key, value in {"distro": "openwrt", "version": "24.10.6", "target": "rockchip/armv8",
                           "arch": "aarch64_generic", "package_manager": "opkg", "version_code": "r999"}.items():
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "mismatch for " + key):
                release.validate_feed(expected, dict(self.published(expected), **{key: value}), url)
        with self.assertRaisesRegex(ValueError, "different official SDK"):
            release.validate_feed(expected, dict(self.published(expected), sdk={"sha256": "b" * 64}), url)
        with self.assertRaisesRegex(ValueError, "Release URL"):
            release.validate_feed(expected, self.published(expected), url + "-other")

    def test_absent_release_or_asset_fails_with_instructions(self):
        metadata = self.metadata()
        matrix = {"include": [metadata]}
        missing = HTTPError("https://github.com/missing", 404, "Not Found", {}, None)
        with patch.object(release, "fetch", side_effect=missing), patch.object(release, "check_asset") as check:
            with self.assertRaisesRegex(ValueError, "firmware builds do not trigger package builds"):
                release.resolve_feeds(matrix, "fangguangyang/openwrt-dist")
            check.assert_not_called()
        with patch.object(release, "fetch", return_value=json.dumps(self.published(metadata)).encode()), \
             patch.object(release, "check_asset", side_effect=missing):
            with self.assertRaisesRegex(ValueError, "No complete published package feed"):
                release.resolve_feeds(matrix, "fangguangyang/openwrt-dist")

    def test_non_apk_feed_metadata_is_rejected(self):
        metadata = self.metadata(version="24.10.6", package_manager="opkg")
        with patch.object(release, "fetch") as fetch:
            with self.assertRaisesRegex(ValueError, "require APK metadata"):
                release.resolve_feeds({"include": [metadata]}, "fangguangyang/openwrt-dist")
        fetch.assert_not_called()

    def test_cli_exports_repository_urls_for_the_firmware_matrix(self):
        import contextlib
        metadata = self.metadata()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, github_output = [root / name for name in ("release.json", "feeds.json", "output")]
            source.write_text(json.dumps({"include": [metadata]}))
            with patch("sys.argv", ["release.py", "feeds", "--metadata", str(source), "--output", str(output)]), \
                 patch.dict("os.environ", {"GITHUB_OUTPUT": str(github_output)}), \
                 patch.object(release, "fetch", return_value=json.dumps(self.published(metadata)).encode()), \
                 patch.object(release, "check_asset"), contextlib.redirect_stdout(io.StringIO()):
                release.main()
            expected = {"amd64": self.published(metadata)["feed_url"]}
            self.assertEqual(json.loads(output.read_text()), expected)
            self.assertEqual(json.loads(github_output.read_text().split("=", 1)[1]), expected)

    def test_local_image_build_rejects_wrong_feed_before_downloading_imagebuilder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts, tools = root / "scripts", root / "tools"
            scripts.mkdir()
            tools.mkdir()
            original = Path(__file__).resolve().parents[1] / "scripts"
            for name in ("release.py", "build-image.sh"):
                shutil.copy2(original / name, scripts / name)
            profile = root / "profiles/amd64"
            profile.mkdir(parents=True)
            (profile / "features").touch()
            metadata = self.metadata()
            source = root / "metadata.json"
            source.write_text(json.dumps(metadata))
            wrong_feed = root / "wrong.json"
            wrong_feed.write_text(json.dumps(dict(self.published(metadata), arch="aarch64_generic")))
            curl = tools / "curl"
            curl.write_text("#!/usr/bin/env python3\nimport os, shutil, sys\nshutil.copy2(os.environ['TEST_FEED'], sys.argv[sys.argv.index('-o') + 1])\n")
            curl.chmod(0o755)
            work = root / "work"
            env = dict(os.environ, BUILD_WORKDIR=str(work), TEST_FEED=str(wrong_feed),
                       PATH=str(tools) + os.pathsep + os.environ["PATH"])
            result = subprocess.run(["bash", str(scripts / "build-image.sh"), str(source), self.published(metadata)["feed_url"]],
                                    env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mismatch for arch", result.stderr)
            self.assertEqual(list((work / "downloads").iterdir()), [])

    def test_build_assembles_features_in_the_apk_device_profile(self):
        project = Path(__file__).resolve().parents[1]
        devices = [
            self.metadata(),
            self.metadata(id="m28c", target="rockchip/armv8", profile="widora_mangopi-m28c", arch="aarch64_generic"),
        ]
        for metadata in devices:
            device = metadata["id"]
            with self.subTest(device=device), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(project / "profiles", root / "profiles")
                shutil.copytree(project / "scripts", root / "scripts")
                (root / "profiles/amd64/features").write_text("# python\n")
                (root / "profiles/m28c/features").write_text(
                    "statistics\n\n  python # Include the Python runtime\npython\n# upnp\n")
                # Core download and validation are tested separately.
                (root / "scripts/prepare-openclash.py").write_text(
                    "from pathlib import Path\nimport sys\nPath(sys.argv[3]).write_text(sys.argv[1])\n")
                tools, downloads = root / "tools", root / "work/downloads"
                tools.mkdir()
                downloads.mkdir(parents=True)
                archive = downloads / "imagebuilder.tar.gz"
                entries = {".config": "", "repositories": "https://example.org/packages.adb\n"}
                if device == "m28c":
                    image_root = "build_dir/target-test/root-rockchip/"
                    for name in ("usr/share/luci/menu.d/luci-app-qmodem-next.json", "etc/config/qmodem", "usr/bin/modem_scand",
                                 "etc/init.d/qmodem_init", "etc/init.d/qmodem_network"):
                        entries[image_root + name] = ""
                    entries.update({
                        "scripts/.fixture": "",
                        "include/image.mk": "define Image/mkfs/ext4\n\tfixture\nendef\n",
                        image_root + "usr/share/qmodem/modem_support.json": json.dumps({
                            "modem_support": {
                                "usb": {"fm350-gl": {"modes": ["rndis"], "pdp_index": "0"}},
                                "device": {"fibocom": {"mediatek": {"vendor_id": ["0e8d"],
                                                                    "product_id": ["7126", "7127"]}}},
                            },
                        }),
                    })
                with tarfile.open(archive, "w:gz") as bundle:
                    for name, text in entries.items():
                        data = text.encode()
                        member = tarfile.TarInfo("builder/" + name)
                        member.size = len(data)
                        bundle.addfile(member, io.BytesIO(data))
                metadata["imagebuilder"] = {"name": archive.name, "sha256": release.sha256(archive)}
                source, feed, arguments = (root / name for name in ("metadata.json", "feed.json", "make-args"))
                source.write_text(json.dumps(metadata))
                feed.write_text(json.dumps(self.published(metadata)))
                commands = {
                    "curl": """case "$4" in
    */build.json) cp "$TEST_FEED" "$6" ;;
    */feed-key.pem) printf 'key' > "$6" ;;
    *) exit 2 ;;
esac
""",
                    "make": """if [ "$1" = image ]; then
    shift
    printf '%s\\n' "$@" > "$TEST_ARGS"
    mkdir -p "bin/targets/$TEST_TARGET"
    touch "bin/targets/$TEST_TARGET/firmware.img.gz"
fi
""",
                }
                for name, text in commands.items():
                    command = tools / name
                    command.write_text("#!/bin/sh\nset -eu\n" + text)
                    command.chmod(0o755)
                env = dict(os.environ, BUILD_WORKDIR=str(root / "work"), TEST_FEED=str(feed),
                           TEST_ARGS=str(arguments), TEST_TARGET=metadata["target"],
                           PATH=str(tools) + os.pathsep + os.environ["PATH"])
                command = ["bash", str(root / "scripts/build-image.sh"), str(source), self.published(metadata)["feed_url"]]
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                options = dict(line.split("=", 1) for line in arguments.read_text().splitlines())
                packages = options["PACKAGES"].split()
                self.assertEqual(packages.count("python3-light"), int(device == "m28c"))
                self.assertNotIn("luci-app-upnp", packages)
                self.assertEqual("telnet-bsd" in packages, device == "amd64")
                self.assertEqual("luci-app-qmodem-next" in packages, device == "m28c")
                self.assertEqual("luci-i18n-qmodem-next-zh-cn" in packages, device == "m28c")
                self.assertNotIn("xmm-modem", packages)
                files = Path(options["FILES"])
                self.assertTrue((files / "etc/apk/keys/custom-feed.pem").is_file())
                self.assertEqual((files / "etc/init.d/zte_moden").is_file(), device == "amd64")
                self.assertEqual((files / "etc/uci-defaults/98-qmodem-m28c").is_file(), device == "m28c")
                self.assertEqual((files / "etc/uci-defaults/94-statistics").is_file(), device == "m28c")
                self.assertTrue((root / "release" / f"{device}-firmware.tar.gz").is_file())


if __name__ == "__main__":
    unittest.main()
