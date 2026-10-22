import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("build_release", Path(__file__).resolve().parents[1] / "tools" / "build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PackageTests(unittest.TestCase):
    def prepare(self, root):
        (root / "app.exe").write_bytes(b"MZ-synthetic-test-binary")
        (root / "LICENSE").write_text("Test license", encoding="utf-8")
        (root / "settings.example.json").write_text('{"username":"","password":"","profile":{}}', encoding="utf-8")
        (root / "profiles").mkdir()
        (root / "profiles" / "custom-template.json").write_text("{}", encoding="utf-8")

    def test_package_allowlist_and_checksums_exclude_personal_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare(root)
            (root / "settings.json").write_text('{"password":"do-not-package"}', encoding="utf-8")
            (root / "campus-connect.log").write_text("private-log", encoding="utf-8")
            files = release.create_assets(root, root / "app.exe", root / "out", "v0.1.0", "a" * 40)
            with zipfile.ZipFile(files[1]) as bundle:
                self.assertEqual(set(bundle.namelist()), {
                    "SRUN-Campus-Connect/SRUN-Campus-Connect.exe", "SRUN-Campus-Connect/LICENSE",
                    "SRUN-Campus-Connect/QUICK_START.txt", "SRUN-Campus-Connect/settings.example.json",
                    "SRUN-Campus-Connect/profiles/custom-template.json",
                })
                self.assertEqual(bundle.read("SRUN-Campus-Connect/SRUN-Campus-Connect.exe"), files[0].read_bytes())
            for line in files[3].read_text().splitlines():
                digest, name = line.split("  ")
                self.assertEqual(digest, release.sha256(root / "out" / name))

    def test_filled_account_example_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare(root)
            (root / "settings.example.json").write_text('{"username":"synthetic-account","password":""}', encoding="utf-8")
            with self.assertRaises(ValueError):
                release.create_assets(root, root / "app.exe", root / "out", "v0.1.0", "a" * 40)

    def test_credentials_in_profile_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare(root)
            (root / "profiles" / "custom-template.json").write_text('{"password":"synthetic-password"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                release.create_assets(root, root / "app.exe", root / "out", "v0.1.0", "a" * 40)


if __name__ == "__main__":
    unittest.main()
