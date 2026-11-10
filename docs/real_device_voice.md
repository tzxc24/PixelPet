# 实物语音交互

启动一轮后，听到一声短音再说话。说完停顿约 1.8 秒，设备用两声短音提示录音结束。
没有说话约 8 秒退出，单次最多 15 秒。三声低音表示这轮语音处理失败。
目前这块板的开始、手动结束和取消由 USB 串口 r、s、c 命令触发。

## 当前音频结构

INMP441 经独立 FreeRTOS 任务采集 20 ms、320 个 PCM16 样本，
通过八帧队列交给语音检测和录音收集逻辑。队列超时作为明确错误处理。
结束或取消时等待采集任务停稳，随后才播放提示音和回复。
整段录音先存入有上限的 PSRAM 缓冲，采集结束再通过 Wi-Fi 上传。

正式语音检测使用 ESP-SR 中的独立 WebRTC VAD。它通过语音特征作出判断。
保留原能量检测的构建选项，用于基线对比。板端当前未加载 WakeNet、
神经 VAD 模型或 AEC。语音转写、DeepSeek、SQLite 和 Edge TTS 继续由 PC 服务处理。

## 构建

当前已核对麦克风和功放的开发板配置在本机 tmp/sdkconfig-sparkbot-voice。
使用以下命令构建，脚本会检查并下载固定版本的 ESP-SR 依赖。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File firmware/build.ps1 -SdkConfig D:/PixelPet/tmp/sdkconfig-sparkbot-voice
```

ESP-SR 固定为 b6774a31118de04742e51ab57dd68c9001fa1091。
仅链接 ESP32-S3 的 libesp_audio_processor.a，构建时校验版本与 SHA256。
依赖保存在 tmp/esp-sr-reference。授权文本在 firmware/third_party/esp-sr-LICENSE.txt。
默认固件配置仍要求分别核对硬件，当前音频批准不启用屏幕或马达。

## 参考

- ESP-SparkBot factory_demo_v1 的采集、检测、队列与 UI 事件结构
  https://gitee.com/esp-friends/esp_sparkbot/tree/d42c5b43e25168fa3592a9c3d113ab5631f47023/example/factory_demo_v1
- 官方 ESP-SR 接口
  https://github.com/espressif/esp-sr/blob/b6774a31118de04742e51ab57dd68c9001fa1091/include/esp32s3/esp_vad.h

## 实物验证记录

2026-11-08，本次固件编译和 10 项 C++ 主机测试通过。
实物确认 ESP-SR 检测器已运行。取消录音后正常释放资源并恢复下一轮待机，
没有生成聊天请求。正常说话的一轮录到约 8.06 秒，自动停止并完成
DeepSeek、Edge TTS 和 I2S 播放。用户确认听到回复。
“小星”仍被识别为“小心”，名字同音字准确性需要继续校准。
实测记录见 output/esp32-sparkbot-upgrade-report.json。


## 连续问答的安静模式（2026-11-08）

串口 `d` 开启连续问答，`c` 停止。连续模式取消每轮开始和结束的提示音；
ESP-SR WebRTC VAD 在设备端检测人声，约 1.8 秒无语音后自动提交。
回答播放完成后自动恢复聆听；安静等待期间不提交背景录音。
单次 `r` 测试仍保留提示音，错误提示仍保留。
目前为半双工，播放期间不录音，不支持边播放边打断；未引入 AEC 或唤醒词。
开录前仍需约 2 秒麦克风稳定时间，请等小星说完稍停再讲话。
新固件需真人复测环境噪声和听感，不将主机测试视为实物听感通过。


## 语音休息和唤醒

开启连续对话后说“小星，休息吧”或“休息吧”。识别到完整口令后，
后端先返回 dialog.state=standby，再生成确认语音。板端仅采集 VAD 判定的语音片段，
record.start purpose=wake 的片段强制交给电脑本地 Whisper，绕过百度和 DeepSeek。
普通待机片段不写聊天、记忆或音频文件。“你好小星”“小星小星”触发唤醒，
只在明确的“你好小心”中允许常见同音字；不匹配长句中的引用。
唤醒后说“我在，想聊什么？”，保留原 conversation_id，继续百度识别和 DeepSeek。
确认短语使用现有 Edge TTS，仅将固定回复文本发送给语音合成服务。
这不是板端 WakeNet，也不是离线独立桌宠；电脑后端、本地 Whisper 模型和局域网必须可用。
待机仍用电且麦克风开启，串口 c 才完全停止语音循环。重启仍默认关闭监听。
没有 AEC，不能在播报时语音打断。每次恢复聆听约有 2 秒麦克风稳定时间。
自动化匹配与模拟协议通过不等于真人唤醒通过；实测见 output/esp32-standby-wake-live-report.json。

## 完整聊天与长期记忆

每次成功识别的用户文字和生成的回复保存到 output/pixelpet.sqlite3 的 messages；
识别失败时没有可信文字，不编造聊天。原始音频不长期保存。
按用户要求，模型现在接收 SQLite 中所有已保存会话的完整文字历史，按消息 ID 排序，
不再限制为最近 20 条或截断每条 2000 字。当前输入只加入一次。
删除或清空的历史不在发送范围内；记忆本仍是另行筛选的重要事实。
本机发送保护上限 LLM_HISTORY_MAX_CHARS 默认 500000 字符，不代表模型 token 容量。
超过本机上限或服务商容量会明确报错并保留用户消息，不静默裁剪或摘要。
历史越长，费用、延迟可能增加。后端诊断 context 显示实际历史条数、字符数和 truncated=false。
实物语音会话 ID 可由 /api/devices/voice/status 查询（需本机令牌）。
网页每 3 秒同步，勾选“跟随实物语音会话”查看实物聊天；手动选历史会自动取消跟随。
记忆本展开时同样自动同步，编辑时不抢占表单；同步不会触发二次语音播放。
完整对话不等于长期记忆。当前仅重要、明确且非敏感事实进入记忆本，普通问答留在聊天记录。


### 模型确认休息时必须执行待机

2026-11-08 修正口头确认与实际状态不一致的问题。
模型响应新增 dialog_state=active/standby。模型答应休息时必须返回 standby；
设备语音后端会在合成/播放前发送 dialog.state，现有固件据此进入待机。
旧模型只返回“我先休息”“那我先睡一会儿”时也由明确自我承诺兜底检测触发。
问题、否定、故事引用不被兜底识别为承诺。
另兼容实际 ASR 出现的“小型休息吧”，以及开头为完整休息指令、后面混入其他句子的录音。
全量 Python 测试 253 项通过；真实 DeepSeek 在隔离数据库测试中返回 standby。
这次无需变更 GPIO 或重新烧录固件；已更新后端服务。


### 唤醒引擎更新：本地关键词检测

此前“Whisper 整句识别后匹配口令”的实物表现不稳定，现已在设备语音待机通道
替换为 Sherpa-ONNX 2.0.1 的离线关键词检测，不再依赖整句转写与短名字置信度阈值。
当前使用官方 zh-en 3M、2025-12-20 模型的 int8 encoder/joiner 与 fp32 decoder，
运行在电脑 CPU，模型与词表由 config/wake_model.json、config/wake_keywords.txt 管理。
接受“你好小星”“你好小心”“小星小星”。按发音检测，避免同音字转写差异。
首次安装运行 `.venv\Scripts\python.exe scripts/setup_wake_model.py`，脚本校验归档与模型 SHA256。
模型缺失会报错；不会自动把待机声音转发百度或 DeepSeek。
普通对话仍用百度识别、DeepSeek 回答、Edge TTS，长期记忆与聊天库不变。
PC 网页自己的旧唤醒按钮仍走网页原流程；本次更新针对真实 ESP32 的语音待机通道。
固件旧日志的“local Whisper only”是旧通道标签，真实引擎以 /api/audio/status 的 wake.provider 为准。
当前固件仍分段上传，背景持续说话时可能等约 15 秒录音上限后才开始检测，不宣称无延迟流式唤醒。
官方录音正例和静音、噪声、历史非唤醒录音负例已验证，真人唤醒仍需现场确认。
官方文档：https://k2-fsa.github.io/sherpa/onnx/kws/index.html
