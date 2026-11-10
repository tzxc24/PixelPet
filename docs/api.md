# V1 API 与协议边界

默认地址 http://127.0.0.1:8765。完整实际 schema 见 /docs 和 /openapi.json。模型密钥不作为任何前端 API 字段。

| 路径 | 方法 | 职责 |
| --- | --- | --- |
| /api/status | GET | 实际 Provider、模型、V1 版本 |
| /api/diagnostics | GET | 依赖、ASR/TTS、FSM、事件元数据及耗时 |
| /api/chat | POST | 非流式，多轮、记忆、保存消息 |
| /api/chat/stream | POST | SSE meta/delta/done/error；只有 done 表示完整验证保存 |
| /api/conversations | GET / POST | 查询 / 新建 |
| /api/conversations/{id}/messages | GET / DELETE | 消息 / 清空 |
| /api/conversations/{id} | DELETE | 删除会话 |
| /api/memories | GET / POST / DELETE | 查询/新增/清空；支持 q/category/since |
| /api/memories/{id} | PATCH / DELETE | 内容、重要度、用户确认 / 删除 |
| /api/memories/export | GET | JSON 导出 |
| /api/audio/status、/voices | GET | 就绪与安装声音 |
| /api/audio/transcribe | POST | audio multipart，10MiB/60秒，真实解码后验证 |
| /api/audio/synthesize | POST | text/voice/rate/volume -> WAV 与真实音频元数据 |
| /api/pet/settings | GET / PATCH | 持久设置 |
| /api/reminders | GET / POST | 提醒管理；due_at 为带时区 ISO |
| /api/reminders/{id} | DELETE | 删除提醒 |
| /api/notifications/poll | GET | 领取到期提醒/已启用限频问候，去重 |
| /api/events、/status | POST / GET | 统一事件、效果与有限审计 |
| /api/devices | GET | 模拟设备与 HW_PENDING 状态 |
| /api/devices/ws | WS | PixelPet 业务 JSON 控制，不接收 Opus |
| /api/assets/rgb565 | POST | RGBA 帧 -> RGB565 little-endian RGB 字节 |

原 /api/health、/api/pet/state、/api/simulator/events、/preview 契约保留用于第一阶段回归；V1 状态和依赖以 /api/status、/diagnostics 为准。

所有请求实际 body 上限 11MiB（包括分块传输），上传单个音频10MiB，WS业务帧16KiB。来源/Host 校验防跨站访问，LAN 显式 Host 和令牌授权；本机是单主人应用，不是多租户账户系统。

情绪 normal/happy/shy/sad/angry/curious/thinking/sleepy/surprised，动作 idle/blink/jump/listen/think/speak/sleep/shake。原八态增加 ANNOYED/ERROR；240×240 导出115200字节，真实屏幕的字节序、RGB/BGR、方向和偏移仍需实机检查。

音频返回 X-Audio-Sample-Rate、Channels、Codec、Duration、Provider、Size-Bytes、Synthesis-Ms，客户端按真实 header 解码。ASR 返回标准化16000Hz mono浮点 PCM 的描述与 elapsed_ms。聊天 done 含 llm_first_token_ms/llm_total_ms，界面结束至声音播完的时间受语音长度影响。
