# Windows 部署与排错

项目：D:\PixelPet。所有模型、工具、构建临时文件在 tmp，运行数据和证据在 output。

## 启动

```powershell
Set-Location D:\PixelPet
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开 http://127.0.0.1:8765，旧页面先刷新。点击“试听小星”测试真实播放；点击“开始说话”授予麦克风权限，说完点“结束并发送”。听不到时检查电脑输出设备/音量、浏览器本站声音权限和设置中音量；诊断应报告 TTS Ready，不能只看嘴巴动画。

默认 Windows SAPI 生成真实 WAV；浏览器语音可在设置中选择。自动发声受安静时段和音量限制，手动试听可用于检查声音。麦克风权限拒绝时可继续文字聊天。语音识别仍可能有同音字错误，页面显示识别文字；不承诺本机语音识别完全准确。

## 安装/模型

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 仅当新电脑不存在 .env 时复制
Copy-Item .env.example .env
```

DeepSeek 密钥只在本机 .env 填写。模型默认 base、CPU int8、最多四线程；当前电脑已下载 tiny/base 到 tmp/models。新电脑先下载：

```powershell
$env:HF_HOME='D:\PixelPet\tmp\huggingface'
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; download_model('base', output_dir=r'D:\PixelPet\tmp\models\faster-whisper-base', cache_dir=r'D:\PixelPet\tmp\models\hub')"
```

模型未安装/下载时 ASR Not Ready，文字聊天保留，不生成假识别结果。当前 .venv 的 Python 解释器在 tmp/python，请勿清理该目录。

## 局域网（默认不开放）

仅当用户决定接设备时，在本机 .env 设置独立 PIXELPET_ACCESS_TOKEN，配置 PIXELPET_ALLOWED_HOSTS 为 localhost,127.0.0.1,::1 以及明确的 PC 局域网 IP，重启并手动用 Uvicorn --host 0.0.0.0。不要使用通配 Host。Windows 防火墙需由用户仅允许对应专用网络/设备来源；本轮未修改防火墙，也未开公网端口。

浏览器初次遇到 401 会提示输入局域网访问令牌（不是 DeepSeek 密钥），只存当前标签会话；所有 API 通过后端。设备 WebSocket 使用 Authorization Bearer，不将凭据放 URL。

## 备份、迁移、测试

```powershell
.\.venv\Scripts\python.exe scripts\backup.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
.\.venv\Scripts\python.exe scripts\mock_device.py
.\.venv\Scripts\python.exe scripts\generate_pinmap.py --check
```

SQLite 备份到 output/backups，文件不覆盖且不包含 .env。恢复前停止服务、备份现库，再用备份替换实际配置的数据库文件；启动会自动迁移保留原数据。output/v1-baseline 是本次扩展前源码和数据库快照。

浏览器测试 scripts/browser_v1_check.js 使用合成音源模拟麦克风，并非真实收音。scripts/smoke_llm.py 为显式少量收费 API 测试，默认 Pytest 不消耗云 API。

固件工具链、编译和硬件步骤分别见 firmware_build.md、hardware_wiring.md、hardware_acceptance.md。
