# SRUN Campus Connect

[简体中文](README.md) | English

A configurable SRUN BX1 campus network client with **live English / Simplified Chinese switching**, manual sign-in and sign-out, connectivity checks and automatic reconnection.

This is a configurable protocol template, not a verified compatibility list for every university.

**[Download Windows x64 EXE — no Python required](https://github.com/libwszu/srun-campus-connect/releases/latest/download/SRUN-Campus-Connect.exe)**

[Portable ZIP](https://github.com/libwszu/srun-campus-connect/releases/latest/download/SRUN-Campus-Connect-Windows-x64.zip) · [Releases](https://github.com/libwszu/srun-campus-connect/releases)

## Getting started

1. Put the EXE in a writable folder and run it. Extract the complete ZIP first if using the portable package.
2. Choose **English** or **简体中文** in the top-right language picker. Labels change immediately and the preference is saved locally.
3. Open **Connection** and enter your campus server base URL, `ac_id` and account suffix, or import a campus profile.
4. Enter your own account and password, save, then select **Sign in** or **Start monitoring**.
5. Restart monitoring after changing connection settings. Closing the app stops monitoring.

The app does not sign in automatically on first launch.

## Campus configuration

If the official portal is `http://portal.example.edu/srun_portal_pc?ac_id=12`, use `http://portal.example.edu` as the base URL and `12` as `ac_id`. A deployment prefix and port are supported if your server requires them.

| Field | Purpose |
| --- | --- |
| `base_url` | Authentication server base URL; no embedded credentials, query or fragment |
| `ac_id` | Access-controller identifier for the campus / network zone |
| `username_suffix` | Optional suffix such as `@campus`; accounts that already contain `@` are preserved |
| `challenge_path`, `portal_path` | Challenge and sign-in/out API paths on the configured server |
| `n`, `type` | Protocol parameters; defaults are `200` and `1` |
| `enc_ver` | Currently `srun_bx1` only |
| `base64_alphabet` | 64 distinct ASCII characters for the deployment's encoding alphabet |
| `client_ip` | Optional IPv4 override; otherwise route detection and the server-reported client IP are used |
| `probe_url` | Internet connectivity test URL |
| `probe_status`, `probe_text` | Expected status and exact response text; a 204 probe requires an empty response |

Find these values in your campus network documentation, official portal or an existing trusted configuration. CAS / SSO, QR-code or SMS flows, 802.1X and non-BX1 algorithms are not implemented. SRUN deployments can also differ in ways that require an adapter beyond changing parameters.

## Profiles and credentials

[Custom template](profiles/custom-template.json) · [SZU parameter example](profiles/szu-example.json)

Examples are bundled in the EXE and shown by the import dialog. A profile contains only campus / protocol settings. Exporting a profile excludes your account, password and UI preferences; importing one does not submit a sign-in request or replace typed credentials.

Your actual account is stored in plain text in local `settings.json`, next to the EXE. Logs are written to `campus-connect.log`. Do not share personal settings or unredacted diagnostic output. These files are ignored by Git and excluded from release packages.

## Monitoring

The default interval is 60 seconds. After two consecutive failures, the app retries sign-in with the configured account, up to the configured limit. Redirects and unexpected captive-portal content are not counted as online. Monitoring and manual actions share an authentication lock.

Keep the app running to monitor. This version does not install a Windows startup task. Check manual sign-in before relying on automatic monitoring.

## Run from source

Python 3.11+ with tkinter:

```powershell
git clone https://github.com/libwszu/srun-campus-connect.git
Set-Location srun-campus-connect
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --lang en
```

Use `--lang zh-CN` for Chinese, or omit the option to use the saved preference.

```powershell
python -m unittest discover -s tests -v
python -m pip install pyinstaller==6.21.0
python -m PyInstaller --noconfirm SRUN-Campus-Connect.spec
```

The executable is written to `dist/SRUN-Campus-Connect.exe`. Release automation builds from clean public source, runs offline tests and packaged startup / module checks, then publishes the EXE, ZIP and SHA-256 checksums.

Tests use mocked servers and synthetic credentials, including a payload regression against the original SZU implementation. No live authentication at other universities has been verified.

## License

[MIT License](LICENSE). BX1 primitives are derived from [libwszu/netdetect](https://github.com/libwszu/netdetect), with the original notice retained. Independent software, not endorsed by a university. Use only your own authorized account and network.
