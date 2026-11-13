# PixelPet V1.2-RC3 当前版本快照

整理日期：2026-11-13。

## 云端语音版

- ESP32-S3 可直接连接部署在服务器上的 PixelPet 后端，上电后连续监听，播完自动恢复收音。
- 支持百度语音识别、DeepSeek Flash 和 Edge 晓伊。语音回复按问题需要展开，可讲完整的中国寓言。
- 「现在几点」按后端设置的时区直接报时。「五分钟后提醒我喝水」由服务器保存，到期后设备在空闲时主动播报。
- 设备先缓冲完整音频再播放。播报期间暂停收音；到期时正在对话的提醒会等到设备空闲。语音提醒内容宜用短句。
- 更新时先部署后端，再更新固件。下面的可选配置只适用于已核对麦克风和扬声器接线的 ESP32-S3 板卡。设备联网参数通过 NVS 单独设置。

在已配置 ESP-IDF v6.1 的 Windows 项目环境中构建：

```powershell
Copy-Item firmware/pixelpet_s3/sdkconfig.continuous.defaults tmp/sdkconfig-continuous
powershell -NoProfile -ExecutionPolicy Bypass -File firmware/build.ps1 -SdkConfig tmp/sdkconfig-continuous
```

构建与接线细节见 [固件构建](firmware_build.md) 和 [固件联网说明](../firmware/pixelpet_s3/README.md)。

## 主要内容

- FastAPI 后端、浏览器像素桌宠、情绪动画与语音设置。
- DeepSeek 对话、百度语音识别、Edge TTS 与 Mock 测试模式。
- SQLite 会话、完整消息记录及长期记忆；每轮发送所有已保存会话的历史，超限明确报错。
- ESP32-S3 的独立 PCM WebSocket 语音通道、VirtualESP32 和固件框架。
- 语音休息与本地关键词唤醒。旧版的待机关键词由后端上的 Sherpa-ONNX 检测。

## 当前验证与限制

- RC2 初始快照记录了 260 项 Python 测试和 11 项 C++ 主机测试通过。
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
