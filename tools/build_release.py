"""Build a clean, bilingual Windows portable release without personal settings."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_assets(root, executable, output, tag, source_sha):
    from campus_connect.config import CampusProfile

    root, output, executable = Path(root), Path(output), Path(executable)
    if not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?(?:[-.][A-Za-z0-9]+)*", tag) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("Use a valid version tag and a full source commit SHA")
    sample = json.loads((root / "settings.example.json").read_text(encoding="utf-8-sig"))
    if sample.get("username") or sample.get("password"):
        raise ValueError("The settings example must not contain credentials")
    CampusProfile.from_dict(sample.get("profile", {}))
    profiles = sorted((root / "profiles").glob("*.json"))
    for path in profiles:
        profile = CampusProfile.from_dict(json.loads(path.read_text(encoding="utf-8-sig")))
        if profile.base_url:
            profile.validate()
    output.mkdir(parents=True, exist_ok=True)
    app = output / "SRUN-Campus-Connect.exe"
    shutil.copy2(executable, app)
    archive = output / "SRUN-Campus-Connect-Windows-x64.zip"
    quick_start = """SRUN Campus Connect / SRUN 校园网助手

Windows 10 / 11 x64. Python is not required. / 无需安装 Python。

1. Extract the complete ZIP, then run SRUN-Campus-Connect.exe.
   完整解压后，双击 SRUN-Campus-Connect.exe。
2. Choose English or 简体中文 in the top-right language picker.
   右上角可即时切换 English / 简体中文。
3. In Connection, enter your campus server base URL, ac_id and account suffix,
   or import a credential-free profile. Enter your own account and password.
   在“连接设置”填写学校服务器、ac_id、账号后缀，或导入学校配置，再填写自己的账号密码。
4. Save and test Sign in before starting monitoring.
   保存后先测试手动登录，再启动自动监控。

Only standard SRUN BX1 deployments are supported; parameters vary by campus.
仅实现标准 SRUN BX1 接口，各学校参数可能不同，可能需要进一步适配。
Credentials are stored locally in plain text in settings.json. Do not share it.
账号密码以明文保存在本机 settings.json 中，请勿共享该文件。
"""
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        prefix = "SRUN-Campus-Connect/"
        bundle.write(app, prefix + app.name)
        bundle.write(root / "LICENSE", prefix + "LICENSE")
        bundle.writestr(prefix + "QUICK_START.txt", quick_start.encode("utf-8-sig"))
        bundle.writestr(prefix + "settings.example.json", json.dumps(sample, ensure_ascii=False, indent=2).encode("utf-8"))
        for path in profiles:
            bundle.write(path, prefix + "profiles/" + path.name)
    metadata = {
        "version": tag, "languages": ["en", "zh-CN"], "platform": "Windows x64",
        "source_commit": source_sha, "python": platform.python_version(),
        "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in (app, archive)],
    }
    info = output / "BUILD-INFO.json"
    info.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    checksums = output / "SHA256SUMS.txt"
    checksums.write_text("".join(sha256(path) + "  " + path.name + "\n" for path in (app, archive, info)), encoding="utf-8")
    notes = """Portable bilingual Windows x64 app — no Python required.

支持中英文即时切换的 Windows 64 位免安装版，无需 Python。

- Run the EXE, or extract the complete portable ZIP first.
- Configure your own campus server, ac_id, suffix and account in Connection.
- School profiles can be imported/exported without account credentials.
- 本程序是可自行配置的标准 SRUN BX1 模板，不代表已实测所有学校。
- 校园参数可填写或导入；账号密码只保存在自己的设备上。

Offline tests, packaged startup and embedded-module checks are run before release. Live authentication at other universities has not been verified.
"""
    (output / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    return app, archive, info, checksums


def validate_binary(executable):
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    archive = CArchiveReader(str(executable))
    names = set(archive.toc)
    assert "LICENSE" in names
    assert any(name.lower().startswith("python") and name.lower().endswith(".dll") for name in names)
    assert not any(Path(name.replace("\\", "/")).name in ("settings.json", "campus-connect.log") for name in names)
    pyz = next(name for name in names if name.upper().endswith(".PYZ"))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "modules.pyz"
        path.write_bytes(archive.extract(pyz))
        modules = set(ZlibArchiveReader(str(path)).toc)
        assert {"tkinter", "requests", "campus_connect.gui", "campus_connect.client", "campus_connect.i18n"} <= modules
        environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        result = subprocess.run([str(executable), "--help"], cwd=folder, env=environment, capture_output=True, timeout=60)
        assert result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise SystemExit("Build on 64-bit Windows with 64-bit Python")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "SRUN-Campus-Connect.spec"], cwd=root, check=True)
    executable = root / "dist" / "SRUN-Campus-Connect.exe"
    validate_binary(executable)
    assets = create_assets(root, executable, root / "release-assets", args.tag, args.source_sha)
    print(json.dumps({"packaged_startup": "passed", "assets": [path.name for path in assets]}))


if __name__ == "__main__":
    main()
