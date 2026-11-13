# PixelPet V1.2-RC3 · 小星

> 当前云端语音版（2026-11-13）支持 ESP32 直连服务器、连续问答、实时报时和定时语音提醒。构建及升级顺序见 [当前版本说明](docs/GITHUB_SNAPSHOT.md)。

RC2 的验收、启动、恢复和硬件联调资料集中在 [发布文档](docs/release_v1.2/V1.2_最终开发报告.md)。Windows 双击 `start_pixelpet.bat`。如果提示旧版本占用端口，先退出旧进程再运行。

V1.1 设备语音联调使用独立 PCM WebSocket。设备诊断入口是 `/device-debug`，VirtualESP32 语音命令为 `.\.venv\Scripts\python.exe scripts\virtual_esp32_voice.py <16kHz单声道PCM16.wav> --output output\v1.1\reply.wav`。见 [设备通信协议](output/v1.1/ESP32_设备通信协议.md) 和 [V1.1 测试报告](output/v1.1/PixelPet_V1.1_测试报告.md)。

V1.0-RC1 的验收记录仍可查阅。真人麦克风十轮验收及物理外设验收单独记录。[RC1 验收报告](output/rc1/RC1验收报告.md)

真实 DeepSeek 对话、SQLite 长期记忆、PC 语音和240×240像素桌宠。ESP32-S3 软件引脚映射已冻结，物理电气未验证，设备驱动默认安全禁用。

## 开始使用

Windows 可双击 `D:\PixelPet\start_pixelpet.bat`。启动器会检查运行环境，显示实际访问地址并识别已运行实例。退出时在启动窗口按 Ctrl+C。详见 [一键启动说明](output/final-v1/一键启动说明.md)。

语音对话可点「点按录音，再点发送」开始和结束采集。右上「诊断」提供语音和 WebSocket 状态。整机软件进度及证据见 [V1 软件完成情况](output/final-v1/软件完成情况报告.md) 和 [自动化测试报告](output/final-v1/自动化测试报告.md)。

电脑端可以在语音区点 **开启「小星」唤醒**，授权麦克风后单独说「小星」。看到聆听状态再说正题，说完停顿约 1.2 秒会自动发送。待机音频只交给本机 Whisper 检测。保持页面打开，点 **关闭语音唤醒** 可结束检测。此功能默认关闭。ESP32 独立唤醒仍待实现和实机验证。

```powershell
Set-Location D:\PixelPet
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开 [小星](http://127.0.0.1:8765/)，已有页面先刷新。点击 **试听小星** 测试声音；点击 **开始说话** 允许麦克风，说完点 **结束并发送**。文字聊天始终保留。旧“模拟录音/播放”只预览硬件状态，与新增的真实语音按钮分开。

**自然声音设置：右上角「设置」→「语音输出」选 Edge →「声音」选音色 →「试听当前声音」。** 语音服务、音色、语速、音量、音调自动保存到 SQLite，其余设置仍点击保存。默认晓伊、语速 +0%、音调 +0Hz、正常音量。可点「恢复语音默认值」。需要联网，回复文字会发送给 Microsoft 的在线语音服务；DeepSeek 负责生成回复，Edge 负责读出来。

[声音对比页](http://127.0.0.1:8765/voice-test) 使用同一句话比较晓伊、晓晓、云希，并显示实际 Provider、参数、耗时和播放状态。**晓梦当前不在实测 Edge 目录中，已标为不可用，不能宣称生成成功。** Edge 失败会明确提示；普通回复可明确降级到离线 SAPI，试听不降级。点击「停止 / 取消」取消当前合成或播放。

本机已安装 Python3.10、依赖、Windows中文声音和 Whisper base/tiny 模型。若听不到，检查系统输出设备、浏览器声音权限、设置音量与安静时段。语音识别可能出现同音字错误；软件合成音频回环和浏览器播放已测试，实际人声收音/物理扬声器音质需用户试听确认。

## 安装、配置和数据

新电脑安装 Python3.10 后：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 仅在不存在 .env 时复制，勿覆盖已配置的密钥
Copy-Item .env.example .env
```

DeepSeek 使用 OpenAI SDK、deepseek-flash、thinking disabled；密钥只在后端 `.env`。没有密钥自动明确进入 Mock，运行中的云错误不会伪装成 Mock。模型和角色分别由配置与 config/character.json 管理。修改环境变量后重启；设置页的模型、名字、音量、语速、声音、麦克风、FPS、安静时段、时区等存 SQLite。

Whisper base 使用CPU/int8，首次新电脑需下载，命令见 [Windows部署](docs/deployment_windows.md)。当前模型在 tmp/models；当前虚拟环境解释器位于 tmp/python，请勿清理这两个目录。ASR/TTS无需额外云密钥；浏览器语音可切换，但不等于设备可用音频字节。

数据库仍为 output/pixelpet.sqlite3，沿用五张表、增量迁移到 user_version3；原始录音不永久保存，聊天会保存到本机。云模式发送当前文字、有界历史和相关记忆给DeepSeek。记忆支持查看、纠正、确认、分类/时间检索、导出与删除；清空会话不等于清空记忆。

```powershell
.\.venv\Scripts\python.exe scripts\backup.py
```

备份在 output/backups，不含.env且不覆盖已有文件；扩展前快照在 output/v1-baseline。局域网默认未开放，只有显式Host白名单与独立Bearer令牌配置后才允许，见部署文档；本轮未改防火墙。它是本机单主人应用，不是多租户账号系统。

## GPIO与固件

用户正式接线文件已复制到 docs/hardware-source-v1.md。**hardware/pinmap.json 是唯一映射源**，用脚本生成 firmware/main/board/pixelpet_pin_config.h。

| 模块 | 软件映射 |
| --- | --- |
| INMP441 SCK/WS/SD | GPIO4/5/6 |
| MAX98357A BCLK/WS/DIN | GPIO7/8/9 |
| ST7789 SCK/MOSI/RST/DC/CS | GPIO14/15/16/17/18 |
| TTP223 / 马达控制 | GPIO13 / GPIO21 |
| BL / 字库CS-F | 未启用；GPIO10仅预留给BL控制 |

已实现安全门控的 SPI ST7789、独立 I2S RX/TX、触摸、马达驱动函数；录音/马达互锁和DMA完成等待有主机测试。ESP-IDF v6.1 的 **esp32s3 原生编译通过**，日志及二进制在 output，未烧录、未激活GPIO。

```powershell
.\.venv\Scripts\python.exe scripts\generate_pinmap.py --check
powershell -ExecutionPolicy Bypass -File firmware\build.ps1
```

不能直接把编译成功当成可接电使用：ST7789 VCC/BL/CS-F、马达供电/阈值/保护、第三方板卡实际引出、功放SD/MODE等均HW_PENDING。详见 [逐线接线](docs/hardware_wiring.md)、[引脚核验](docs/pinout_validation.md)、[编译证据](docs/firmware_build.md)、[到货验收](docs/hardware_acceptance.md)。

小智原生音频网关、Opus互通、设备端完整动画任务和Wi-Fi/BLE集成仍PARTIAL；当前 JSON WebSocket 是 PixelPet 业务协议，不宣称原生小智兼容。采用独立网关方案B，锁定的上游commit见 [架构决策](docs/architecture_decision.md)。

## 测试

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test.ps1
.\.venv\Scripts\python.exe scripts\mock_device.py
```

默认Pytest不调用收费API，使用隔离数据库和Mock/本地HTTP；保留全部第一阶段回归。真实少量DeepSeek测试使用 scripts/smoke_llm.py；浏览器文字回归为 scripts/browser_check.js，合成音源语音链路为 scripts/browser_v1_check.js。

新增语音验证：`node tests/audio_player_check.cjs`；实际浏览器检查 `scripts/browser_voice_check.js`。运行 `.\.venv\Scripts\python.exe scripts\verify_natural_tts.py` 会联网生成三种可用音色的同句 WAV，保存到 output/natural-voice；加 `--with-chat` 另在隔离数据库中执行一次真实 DeepSeek→Edge 验证。自然语音说明、修改清单与回退方法见 [语音优化报告](docs/natural_tts_report.md)。

完整结果见 [测试报告](docs/test_report.md)。原生构建日志 output/firmware-idf-build-final.log；C++主机测试 output/firmware-host-report.txt；Python回归 output/v1-pytest-final.log；浏览器与截图 output/playwright；语音回环 output/speech-loopback-verification.json。

## 现在可做与待做

- DONE：真实文字/流式对话、记忆持久化管理、PC录音/本地ASR/Edge自然语音/SAPI离线兼容、统一WAV播放与取消、音色设置和对比页、设置/时钟/限频问候/本地提醒、10态像素模拟、RGB565导出、触摸/震动FSM、设备WS控制模拟、GPIO统一、主机测试和S3原生编译。
- PARTIAL：实际人声收音和物理音质未验证；小智原生网关/Opus、完整端侧业务调度和Wi-Fi/BLE尚未集成。
- HW_PENDING：所有物理接线、供电、屏幕、I2S时序与音质、触摸、马达和无线实机测试。

主动问候默认关闭，开启后只在09/14/19开始的当前本地时段各至多一次固定问候；提醒仅在服务和页面运行时通知，安静时段/每日上限/持久去重有效，关闭电脑不承诺送达。

架构见 docs/architecture.md，接口见 docs/api.md，语音细节见 docs/speech.md。

## 实物设备联通

2026-11-08，ESP32-S3 N16R8 通过 COM4 烧录设备通信版本。
电脑设备服务地址为 http://10.212.82.141:8765，板子地址为 10.212.82.140。
设备使用 PixelPet business-v1 WebSocket 和独立访问令牌连接。
当前局域网联调使用明文 WS。设备服务单独绑定这块 WLAN 的 IPv4 地址。

启动设备服务使用以下命令。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_device_server.ps1
```

局域网地址及访问令牌保存在本机 tmp/device-lan-private.json。
Wi-Fi 和设备 NVS 配置也在 tmp 目录，均被 Git 忽略。
更换网络或电脑地址后，需要同步调整服务地址与板端配置。
设备服务运行时，访问 /api/devices 可查看当前设备状态，接口需要访问令牌。

串口实测日志保存在 output/esp32-device-runtime.log。
本轮硬件验证仅覆盖板子启动、PSRAM 和设备网络通信。
麦克风、功放、屏幕、触摸和马达仍须逐项接线与验证。

实物语音的提示音、自动结束规则、ESP-SR 固定依赖和采集队列见
[实物语音交互](docs/real_device_voice.md)。


### 2026-11-08 语音待机、网页同步和完整历史

详见 [实物语音说明](docs/real_device_voice.md)。
“小星，休息吧”进入本地待机，“你好小星”恢复连续对话；待机识别使用电脑本地 Whisper，
不向百度或 DeepSeek 发送待机片段，仍需要电脑和局域网。串口 d 开始，c 完全停止。
真人口令测试状态以 output/esp32-standby-wake-live-report.json 为准。
网页“跟随实物语音会话”与记忆本自动同步，不重复播放历史语音。
现在每轮向模型发送所有已保存会话的完整文字历史，不再只取最近 20 条。
LLM_HISTORY_MAX_CHARS 是本机保护上限（默认 500000 字符）；超限报错，不静默裁剪。
聊天仍保存在 output/pixelpet.sqlite3；原始录音不长期保存。


### 本地关键词唤醒引擎更新

真实 ESP32 的待机通道已从 Whisper 整句识别换为本地 Sherpa-ONNX 关键词检测。
安装 requirements.txt 后运行 `.venv\Scripts\python.exe scripts/setup_wake_model.py`。
模型保存在项目 tmp/models，按 config/wake_model.json 校验；词表是 config/wake_keywords.txt。
唤醒词为“你好小星”“你好小心”“小星小星”；仍需电脑后端与局域网。
详细限制与测试记录见 docs/real_device_voice.md 和 output/keyword-wake-engine-verification.json。
