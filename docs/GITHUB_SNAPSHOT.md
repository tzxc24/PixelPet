# PixelPet V1.2-RC2 当前版本快照

整理日期：2026-11-10。此仓库保存当前工程源码，不表示所有硬件与唤醒场景已验收。

## 主要内容

- FastAPI 后端、浏览器像素桌宠、情绪动画与语音设置。
- DeepSeek 对话、百度语音识别、Edge TTS 与 Mock 测试模式。
- SQLite 会话、完整消息记录及长期记忆；每轮发送所有已保存会话的历史，超限明确报错。
- ESP32-S3 的独立 PCM WebSocket 语音通道、VirtualESP32 和固件框架。
- 语音休息与本地关键词唤醒。当前设备待机采用电脑上的 Sherpa-ONNX，仍需要电脑后端及局域网。

## 当前验证与限制

- 本次上传前 Python 测试 **260 项通过**，C++ 主机测试 **11 项通过**。
- 麦克风采集、喇叭播放、连续问答和进入待机已有实物验证记录。
- 本地唤醒检测已有命中记录，但背景噪声下的稳定性仍在联调，不承诺每次可靠唤醒。
- 当前音频分段上传；背景持续说话时可能等到约 15 秒录音上限后才检测唤醒词。
- 播放期间不录音；暂不支持语音打断。屏幕、触摸、马达等模块须按文档逐项验收。
- PixelPet 自定义协议与小智协议通过独立适配层处理，不直接宣称协议相同。

## 从干净副本启动

在 Windows PowerShell 中，进入项目目录后运行：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\setup_wake_model.py
.\start_pixelpet.bat
```

将自己的密钥填写到本机 `.env`。没有模型密钥时可使用 Mock 模式。百度识别、本地 Whisper、设备联网及 ESP-IDF 构建的额外配置见对应文档。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

固件构建依赖 ESP-IDF 环境；请阅读 [固件构建](firmware_build.md)，不要把 PC 测试视为硬件验证。

## 文件与数据边界

本仓库不上传 `.env`、Wi-Fi/设备凭证、聊天数据库、录音、模型权重、编译产物、调试日志、虚拟环境与 `tmp/`、`output/`。

原文档中的 `output/` 链接指向本机生成的验收资料，不包含在公开仓库中。运行后的数据库默认是 `output/pixelpet.sqlite3`。模型由下载脚本获取并校验 SHA256，不随源码上传。

- [实物语音与唤醒说明](real_device_voice.md)
- [设备通信协议](release_v1.2/V1.2_设备通信协议.md)
- [接线与 GPIO](release_v1.2/V1.2_GPIO与硬件接线.md)
- [Windows 部署](deployment_windows.md)

第三方组件的许可文件保留在对应目录。公开上传不另行改变本项目的许可条件。
