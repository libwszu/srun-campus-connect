# SRUN 校园网助手 · SRUN Campus Connect

简体中文 | [English](README.en.md)

可自行配置学校参数的 SRUN BX1 校园网客户端，支持**中英文即时切换、手动登录 / 注销、联网检测和断线自动重连**。这是通用配置模板，不是已经实测所有学校的认证工具。

**[下载 Windows 64 位免安装 EXE](https://github.com/libwszu/srun-campus-connect/releases/latest/download/SRUN-Campus-Connect.exe)**

[便携 ZIP 包](https://github.com/libwszu/srun-campus-connect/releases/latest/download/SRUN-Campus-Connect-Windows-x64.zip) · [发布页面](https://github.com/libwszu/srun-campus-connect/releases) · [源码 ZIP](https://github.com/libwszu/srun-campus-connect/archive/refs/heads/main.zip)

## 下载后使用

1. 将 EXE 放在自己的可写文件夹后双击运行，无需安装 Python。使用 ZIP 时请先完整解压。
2. 右上角选择 **简体中文 / English**，语言即时切换并在本机保存。
3. 打开“连接设置”，填写学校的认证服务器根地址、`ac_id` 和账号后缀；也可“导入学校配置”。
4. 填写自己的校园网账号和密码，保存后点击“登录”或“启动监控”。
5. 修改连接设置后，停止并重新启动监控，让新参数生效。关闭程序会停止监控。

程序首次启动不会自动登录。默认界面为英文，也可用 `--lang zh-CN` 启动中文界面。

## 学校参数怎么填写

例如官方门户网址是 `http://portal.example.edu/srun_portal_pc?ac_id=12`：服务器根地址填写 `http://portal.example.edu`，`ac_id` 填写 `12`。如果部署在子路径或使用不同 API，需要按学校实际情况修改。

| 配置 | 说明 |
| --- | --- |
| `base_url` | 认证服务器根地址，可包含端口或部署前缀；不要包含账号、密码、查询参数和片段 |
| `ac_id` | 学校 / 区域的接入控制编号，通常可从官方门户网址看到 |
| `username_suffix` | 如 `@campus`、`@isp`；无后缀时留空。已带 `@` 的账号不会重复拼接 |
| `challenge_path` | 默认 `/cgi-bin/get_challenge` |
| `portal_path` | 默认 `/cgi-bin/srun_portal`，用于登录和注销 |
| `n`、`type` | 默认 `200`、`1`，按学校部署调整 |
| `enc_ver` | 当前实现支持 `srun_bx1` |
| `base64_alphabet` | 认证编码使用的 64 个不同 ASCII 字符，部分部署可能不同 |
| `client_ip` | 可选本机 IPv4。留空时根据到认证服务器的路由推断，并优先使用服务器返回的客户端 IP |
| `probe_url` | 联网检测网址，与认证服务器地址分别配置 |
| `probe_status`、`probe_text` | 预期响应状态与内容，避免将未认证时跳转的登录页面误认为已联网；使用 204 时应为空响应 |

参数应来自学校网络中心、官方门户或你自己的已知配置。需要 CAS / SSO、扫码、短信验证码、802.1X 或其他算法的系统不属于此模板的直接兼容范围。不同 SRUN 版本也可能需要额外适配。

## 可导入的配置模板

- [通用空白模板](profiles/custom-template.json)：先填写服务器地址，默认参数面向常见 BX1 接口。
- [深大参数示例](profiles/szu-example.json)：用于展示 `ac_id` 和账号后缀的设置；使用前仍需确认当前网络环境。

EXE 内置这些示例，“导入学校配置”会优先打开模板目录。也可选择自己保存的 JSON。

“导出学校配置”只导出学校 / 协议参数，**不导出账号、密码或界面设置**。导入学校配置不会覆盖已输入的账号密码，也不会直接发起认证。

## 自动监控

默认每 60 秒检测一次；连续两次不符合联网检测条件后，按配置使用同一账号重试登录。重试次数为 1–10 次，等待可中断。首次使用建议先确认手动登录成功，再开启自动监控。

监控和手动登录共享认证锁，防止同一程序同时提交多个登录请求。程序不安装 Windows 启动项；如需持续监控，请保持程序运行。

## 本机配置与隐私

`settings.json` 和 `campus-connect.log` 保存在 EXE 所在目录；源码方式保存在项目目录。账号密码以明文保存在自己的 `settings.json`，请勿共享该文件。

仓库和发布包只含空白账号示例及无账号的学校参数模板，不含用户个人配置。Git 忽略本机设置、日志和生成的程序。反馈问题前请移除账号、密码、IP 及其他个人信息。

## 源码运行

Python 3.11+，需要 tkinter。Windows PowerShell：

```powershell
git clone https://github.com/libwszu/srun-campus-connect.git
Set-Location srun-campus-connect
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --lang zh-CN
```

英文启动：`python app.py --lang en`。默认读取本机已保存的语言偏好。

## 测试与构建

```powershell
python -m unittest discover -s tests -v
python -m pip install pyinstaller==6.21.0
python -m PyInstaller --noconfirm SRUN-Campus-Connect.spec
```

输出为 `dist/SRUN-Campus-Connect.exe`。GitHub Actions 从干净源码构建并检查内置模块、Python 运行库、打包启动和配置隐私，再生成发布包及 SHA-256 校验表。

测试覆盖模拟服务器下的协议和界面行为，以及与原深大实现的认证参数一致性。未对其他学校执行真实登录，不能据此宣称兼容所有 SRUN 校园网。

## 许可与来源

[MIT License](LICENSE)。BX1 加密原语派生自 [libwszu/netdetect](https://github.com/libwszu/netdetect)，保留原版权声明。此项目不是任何学校的官方软件，仅用于自己获授权的账号和网络。
