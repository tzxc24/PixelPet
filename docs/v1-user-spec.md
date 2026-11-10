# PixelPet V1.0｜硬件未到货阶段完整开发任务书

> **提交对象：Codex / GPT 编码代理**  
> **文档日期：2026-11-05**  
> **项目路径：`D:\PixelPet`**  
> **当前状态：已经存在第一阶段项目，严禁无检查地重建或覆盖**

## 0. 给编码代理的最高优先级指令

你现在是 PixelPet 项目的主开发工程师，负责在现有代码库上尽可能完整地实施 V1.0，而非仅给出建议或伪代码。**请先检查真实文件、Git 状态、数据库、依赖、路由及测试，再修改工程；不要认为本文件描述的既有功能一定正确，要以实际代码为准。**

- **现在可以完成的代码全部尽量实现、测试、文档化**，包括 DeepSeek、SQLite、电脑语音、像素动画、模拟触摸与震动、事件总线、通信模拟、设备接口、固件框架。
- **凡是必须有硬件才能确认的事项，只能标记为 `HW_PENDING`**：屏幕点亮、实际录音质量、功放音量、马达驱动阈值、TTP223 电平、实际 GPIO 排布、真实 Wi-Fi/BLE 稳定性等。不得写“已通过硬件测试”。
- **不得破坏现有第一阶段功能**；先运行其原有测试，新增测试后再全量运行。
- **一次完成尽可能多的可执行工作**，不要每写一个文件就请求用户确认；遇到非关键阻塞可使用可切换的 Mock/Adapter 并明确记录，不要用假实现冒充真实功能。
- 不要把真实 DeepSeek 密钥写进代码、文档、输出、日志、提交记录，也不要在前端暴露；只允许读取本机环境变量或本地忽略版本控制的配置。
- 修改现有项目时尽量采取小步兼容、带迁移脚本、可回滚的方式。先做 Git checkpoint（若仓库已有 Git）。

## 1. 已知背景与最终目标

### 1.1 用户与运行环境

- Windows 64 位电脑；Intel Core Ultra 7 265K；实际系统截图约 12GB 内存，无独立显卡；D 盘有足够空间。
- 本地服务端和 SQLite 长期记忆部署在 PC 上；大模型通过用户已有的 **DeepSeek API** 调用。
- **本地部署并不代表完全离线**：DeepSeek 请求会把必要聊天文本/检索记忆发送至云端；可选的云 ASR/TTS 也会传输语音或文本。前端必须对此提供明确说明。
- 一期硬件预算约人民币 50 元上下；优先快速验证，不做定制 PCB、锂电池和完整外壳。
- 已有项目：`D:\PixelPet`。根据最近的 Codex 截图，已有 FastAPI、SQLite 五类数据表、浏览器模拟器、8 种像素动画、演示聊天和模拟硬件，曾报告通过 27 项后端测试和 34 项浏览器检查。**此信息仅为外部报告，需在本地复核。**

### 1.2 角色与交互目标

- 产品名：`PixelPet`；默认名字：`小星`；性格：`cute`（可爱、好奇、活泼、有适度撒娇但不机械重复）。
- 对话方式：**触摸唤醒/按住或点击后开始录音**；优先做半双工，先录制再回复。支持文字聊天调试。
- 长期记忆：存 PC SQLite，跨会话、重启仍能检索，用户可查看、纠正、删除。
- 多模态反馈：240×240 像素动画、AI 语音回复、TTP223 触摸、微型震动马达；带时间显示、基本情绪与生活节律。
- 最终验收示例：用户告诉小星正在做 ESP32 桌宠，关闭程序重开，再问“我最近在做什么”，能基于真实记忆回答；摸头时屏幕切换、声音和震动按规则响应。

## 2. 锁定硬件（实际到货前保持可配置）

| 项目 | 型号/条件 | 备注 |
| --- | --- | --- |
| MCU | ESP32-S3 N16R8 开发板 | 16MB Flash + 8MB PSRAM，商家页面价格约 ¥21.51，未焊排针 |
| 显示 | 1.33 英寸 ST7789 TFT，240×240，SPI，10 针 | 页面列出 GND、VCC、SCL、SI、SO、RST、DC、CS、CS-F、BL；存在字库片选；控制逻辑、电源和 BL 细节待核实 |
| 麦克风 | INMP441 I2S 数字麦克风 | 3.3V 供电，具体引脚随模块实物核对 |
| 功放 | MAX98357A I2S | 优先选带合适接线端子的模块；扬声器不接地 |
| 喇叭 | 8Ω 2–3W 小型扬声器 | 功率、阻抗与实际功放板匹配 |
| 触摸 | TTP223（或 S3 自带触摸作为备选） | 用户已决定加入实体触摸；优先 TTP223，确认点动/高电平工作模式及 3.3V IO 兼容性 |
| 震动 | 10mm、厚 2.7mm 扁平震动马达 + MOS 驱动一体模块 | 商品说明高电平触发、支持 PWM，但**供电范围及 3.3V 高电平阈值未确认** |
| 联网 | S3 自带 Wi-Fi / BLE | BLE 用于后续配置，AI 走局域网 Wi-Fi |
| 供电 | USB-C 5V；模块按规定分配 3.3V/5V | 共地；检查 USB 供电稳定性 |

### 2.1 引脚策略：严禁提前写死成“最终接线图”

统一创建 `hardware/pins.example.yaml`、固件 `board_config.h` 或等价配置，并附注 **`PROVISIONAL / 待实物确认`**。先预估资源：

- ST7789：SCK、MOSI、CS、DC、RST 共 5 GPIO，BL 可选再用 1 GPIO；SO 一般不需要读回，CS-F 要确认外设空闲处理方式，不能仅凭名字假设悬空永远安全。
- INMP441：BCLK、WS、DIN 共 3 GPIO。
- MAX98357A：BCLK、WS、DOUT 共 3 GPIO。第一版按**独立 I2S TX/RX 引脚**规划；若考虑共用时钟，必须通过官方驱动能力、实际主从/采样时钟验证后再合并，不能直接短接。
- TTP223：数字 GPIO 1 路；震动马达 MOS 控制：GPIO 1 路。
- 不额外占用 GPIO：Wi-Fi、BLE；但需考虑开发板已占用的 USB、启动、Flash/PSRAM、特殊 GPIO。
- **到货后以商品实物丝印、模组资料和开发板引脚图为准**，将暂定针脚写进专用 board 文件，不散落在多处源码。

### 2.2 安全与驱动提醒

- 马达不得直接接 MCU GPIO；用 MOS 驱动模块，验证续流/保护和供电规格。
- GPIO 的 3.3V 高电平是否能驱动该模块，需查 MOS 管/驱动电路参数或实测；当前不宣称已通过。
- ST7789 背光 `BL` 的供电/限流/控制不能猜测，板载电路确认后才接。
- 录音时禁用震动和长时喇叭播放，避免机械噪声及回声；V1 使用半双工。
- 浏览器模拟器中“触摸/震动模拟”只显示指令与动画，**不代表 GPIO 已通过实测**。

## 3. 推荐工程架构

采取 **“现有 FastAPI 应用 + 统一业务服务层 + 小智兼容适配器”** 的渐进方案。**不要直接重写小智协议，也不要强行把两个服务器的同名路由混到一起。**

```text
D:\PixelPet\
  backend/                    # 已有 FastAPI，尽量沿用
    api/                      # REST、WebSocket、健康/配置接口
    ai/                       # DeepSeekProvider、MockProvider、响应校验
    dialogue/                 # 会话管理、上下文长度控制、角色提示词
    memory/                   # SQLite 记忆提取、去重、检索、审计、导出/删除
    speech/                   # ASR/TTS provider 接口与实现
    pet/                      # 情绪、状态机、定时行为、动作决策
    devices/                  # DeviceService、MockDevice、XiaozhiAdapter
    events/                   # 类型化事件总线与审计
    db/                       # 现有模型/迁移/索引/备份
  frontend/                   # 现有浏览器模拟器
    ...                       # 240×240 画布、像素帧、输入区、诊断面板
  firmware/                   # 参考小智官方 repo 或独立子目录
    pixelpet_s3/              # 自定义板级配置和用户逻辑
  shared/                     # JSON schema / OpenAPI / 协议类型定义
  tests/                      # 单测、接口测试、端到端、硬件跳过测试
  scripts/                    # 启动/自检/迁移/备份/格式化脚本
  docs/                       # 本文档、架构、接线待确认、部署、故障排查
  .env.example
  .gitignore
  README.md
```

若现有目录与建议不同，**不要为了目录美观大规模迁移**，只需实现相同职责与清晰模块边界。

### 3.1 必须先定义抽象接口

- `LLMProvider.reply(context) -> structured reply / streamed chunks`。
- `MemoryRepository`: save/search/update/delete/export。
- `ASRProvider.transcribe(audio) -> text`。
- `TTSProvider.synthesize(text) -> audio + codec metadata`。
- `DeviceAdapter.send(event) / receive(event)`。
- `PetEngine.handle_event(event) -> list[effect]`。
- `ClockService`, `NotificationScheduler`, `SettingsService`。

依赖注入或配置切换真实版与 Mock 版，**禁止业务层直接引用 GPIO、特定浏览器 API 或具体模型 SDK**。

## 4. 本阶段要全部实现的功能清单

### A. DeepSeek 真实聊天（P0）

1. 官方 OpenAI 兼容接口：`https://api.deepseek.com`；默认模型 `deepseek-flash`，模型名称作为配置项；`DEEPSEEK_API_KEY` 在本地环境变量中。
2. 普通语音聊天默认非思考模式：ChatCompletions 的 `extra_body={"thinking":{"type":"disabled"}}`，实际行为以官方 SDK/接口为准；复杂问题可配置切换。
3. 支持多轮上下文、超时、有限重试、流式文本、取消请求、网络断开、余额不足等错误提示。
4. 按真实身份/会话隔离消息，禁止跨用户串话。后端保存 user/assistant 消息以及失败状态；在日志中隐藏敏感文本及密钥。
5. 返回 `reply`、`emotion`、`action`、`conversation_id`，由严格 schema 校验。模型返回无法解析时回退文本、安全默认情绪和动作。
6. 对话结果可被前端显示，也可送入 TTS；文本发声必须经过统一 `speech` 服务。
7. 对话中可以使用可检索的长期记忆，但不要凭空宣称“记得你”。

推荐 `.env.example`（仅占位，不写真实密钥）：

```dotenv
APP_ENV=development
API_HOST=127.0.0.1
API_PORT=8000
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_THINKING=disabled
LLM_TIMEOUT_SECONDS=45
MEMORY_DB_PATH=./data/pixelpet.db
DEVICE_MODE=simulator
SPEECH_ASR_PROVIDER=local_whisper
SPEECH_TTS_PROVIDER=browser_or_local
ENABLE_PROACTIVE_GREETING=false
```

**具体变量名可按现有代码规范调整；不能出现多套冲突配置。**

### B. 长期记忆 + 数据治理（P0）

1. 检查并沿用已有 5 张表结构。必要时通过可逆或可追踪迁移补充字段、索引，而非直接删除数据库重建。
2. 保存会话、消息、用户画像、关键事实、来源会话、创建/更新日期、重要程度和用户确认状态。
3. `memory extractor` 以规则/LLM 提取少量有价值事实；重复合并、冲突更新、时间衰减可配置；不将每句话都自动入库。
4. `memory retrieval` 首选 FTS5 或 SQLite 关键词+分类/时间筛选；检索结果标识来源和置信度；后续可替换为向量检索。
5. 会话记忆与长期记忆分开。LLM 上下文：系统角色、当前任务、最近 N 轮、相关前 K 条记忆；控制 token 和成本。
6. 前端增加“我记得什么”面板：查看、纠错、删除、导出、清空，支持备份和数据迁移。
7. 密码、金融信息等敏感内容默认不自动保存；用户明确授权前不主动采集敏感信息。
8. 验收：新建会话或重启 PC 服务后，仍可准确召回保存的主人昵称、喜好或项目事实；删除后不能再次检索到。

### C. PC 真语音闭环（P0，硬件未到可测试）

1. 前端使用浏览器麦克风获取权限并录音，显示音量波形、录音时长和录音状态；后端接收有限大小的音频文件。
2. 做完整 ASR -> DeepSeek -> TTS 链路。**DeepSeek 是 LLM，不是默认语音识别或语音合成服务**。
3. 默认不依赖云 ASR 密钥：优先实现可选 CPU 版 `faster-whisper` tiny/base（适合 12GB RAM；需要首次下载模型），对中文效果不足时允许选择更大模型或兼容云 ASR 的 Provider。
4. TTS：先做 PC 浏览器 `speechSynthesis` 可听验证；再增加可以输出实际音频文件/字节流的后端 TTS Provider（如 Windows SAPI 或已配置的在线 TTS）。**网页语音合成不是未来 ESP32 的音频文件接口**，必须将两者区分。
5. 采样率、声道、编码形式、文件大小、超时全部作为音频元数据传递；统一处理格式转换，避免播放器误把 PCM 当 Opus。
6. V1 半双工：`IDLE -> LISTENING -> THINKING -> SPEAKING -> IDLE`；播音期间不自动录音，避免回声。
7. ASR/TTS 没安装或模型未下载时优雅降级到文字版，不要报成已完成真实语音。
8. 录音与语音缓存默认不永久保存；确需保存时有明确开关和保留期限。

### D. 240×240 ST7789 屏幕模拟器（P0）

1. 已有 8 种动画先做回归检查；将模拟器画布按 ST7789 240×240 显示区域设计，角色不依赖页面 DOM 任意尺寸。
2. 至少状态：IDLE、HAPPY、SHY、LISTENING、THINKING、SPEAKING、SLEEPY/SLEEP、SURPRISED、ANNOYED、ERROR。
3. 动画资源使用可复用 sprite sheet / 帧序列 / 像素绘制，配置 FPS 与内存占用；可导出供 ESP32 使用的 RGB565 资源，注明 endian 与颜色顺序待实机校验。
4. 在页面显示当前时间、网络连接、麦克风/扬声器状态；不遮挡主表情。
5. 提供情绪/动作实时事件面板和动画预览菜单；未来硬件共用动作名与事件 schema。

### E. 触摸与震动反馈（P0 模拟、P1 硬件）

1. PC 页面模拟 `touch_down` / `touch_up` / `tap` / `double_tap` / `long_press`，长按阈值可配置，需防抖。
2. TTP223 数字输入为首选；也可后续保留原生电容触摸实现。不要同时硬编码两套电极接线。
3. 定义 `haptic.pulse(duration_ms, strength)`、`haptic.pattern(name)`。支持 `short`、`double`、`long`；在模拟器中通过 UI 状态/震动图标显示。
4. **真实震动强度 PWM 受驱动模块兼容性影响，不能提前保证。** 硬件到货后先测开关，再测 PWM。
5. 长按进入录音、松开结束录音；轻点展示开心，双点害羞；如果交互优先级冲突，语音录音优先且确保不重复触发。
6. 马达动作在麦克风录音阶段禁用或延迟；夜间静音、震动开关和触觉强度可配置。

### F. 时间、日常行为与主动关怀（P1）

1. PC 本地时钟驱动，支持时区配置、24h/12h、睡眠窗口。
2. 主动问候默认**关闭**，用户开启后可在合理频率内提醒，并提供“免打扰”和每日次数上限。
3. 情绪状态随对话上下文、互动频率与时间变化；不得靠重复随机对话高频打扰。
4. 可选任务提醒：创建/查看/删除本地提醒；精确执行时间，重复提醒有去重机制。
5. 关机后不承诺提醒自动发送；除非日后安装系统任务/服务。

### G. 本地设置与管理（P1）

- 浏览器设置页：宠物名字、音量、麦克风输入设备、语音、说话速度、屏幕亮度（模拟）、震动、性格、安静时段、时区、AI/ASR/TTS provider、DeepSeek 模型名。
- 主界面提供明确的连接状态：`Mock`、`DeepSeek Live`、`ASR Ready`、`TTS Ready`、`ESP32 Pending`。
- 一个操作日志/调试面板区分：前端事件、后端事件、LLM 请求、记忆命中、音频服务状态。敏感字段做脱敏。
- 在本机 `127.0.0.1` 模式下可直接测试；局域网开放时要启用身份校验，不能将设置/记忆 API 裸露给同网所有设备。

### H. 设备通信及小智兼容（P1 现在开发，实机后验证）

1. **先阅读小智官方固件、后端和协议文档，并记录具体 commit/版本。** 官方有 WebSocket 与 MQTT+UDP 两套传输；首版选定一个，不同时实现两个复杂协议。
2. 主工程已使用 FastAPI，不应自创“与小智完全兼容”的说法。建议将小智服务端作为**独立进程或独立 adapter**，使用 `XiaozhiAdapter` 对接已验证的官方协议，避免重新造 Opus 音频链路。
3. 两条实施路径必须在 `docs/architecture_decision.md` 中二选一并解释原因：
   - A（优先）：复用 `xinnan-tech/xiaozhi-esp32-server` 音频服务，PixelPet 的 DeepSeek/记忆/情绪以插件或适配器加入；
   - B：保留 PixelPet FastAPI 主服务，在其外侧做官方小智协议适配网关；不要未经协议测试宣称直连兼容。
4. 先用模拟 client 走 `connect -> hello -> audio start/stop -> response -> disconnect/reconnect`；音频的 Opus 参数、包帧长度、控制消息需与选定官方版本保持一致。
5. 区分自定义的 PixelPet 业务事件（JSON）与小智原生通信消息，不要将自定义 JSON 直接推到小智设备端导致不兼容。
6. 用户已有 Windows PC 无公网服务，优先局域网固定/可配置 IP；断线重试、心跳、超时、重连必须有模拟测试。
7. 为 BLE 参数配置定义抽象特征与数据结构，**到货前只做协议定义和模拟，不声称 BLE 实测成功**。

### I. ESP32-S3 固件预开发（P1 现在编写，实机后验证）

1. 基于官方 `78/xiaozhi-esp32` 学习或派生，按其自定义板卡指南建立**单独的 PixelPet board**，不要覆盖现有厂商板的配置。
2. 官方当前最低 ESP-IDF v6.0.1，推荐 `release/v6.1`；在 Windows 上按真实环境支持安装与构建，若没装 ESP-IDF，记录前置条件和跳过原因。
3. 实现或预留模块：`BoardConfig`、`Display(ST7789)`、`AudioInput(INMP441)`、`AudioOutput(MAX98357A)`、`Touch(TTP223)`、`Haptic(MOS driver)`、`WiFi`、`BLE`、`Clock`、`PetState`。
4. SPI 驱动：处理 240×240、屏幕 offset、颜色顺序、背光；**具体初始化/背光电压/字库片选方式需要实物型号确认**。
5. I2S：输入与输出独立参数、可配置时钟/数据引脚；先检查官方 `NoAudioCodec`/相关适配方式，不要假设 MAX98357A 是独立音频编解码器。
6. TTP223 / 电机采用**可配置引脚**，通过抽象事件调用，避免端侧直接耦合聊天逻辑。
7. 支持编译单元测试、host mock、日志，但绝不能把“源码可编译”写成“硬件已验证”。
8. 完成 `docs/hardware_pending.md`，列出购买页、待拍实物图、引脚表、BL 电路、电压、电流、马达驱动阈值、真机测试步骤。

## 5. 推荐 API / 事件协议（先实现并以实际代码调和）

### 5.1 REST

- `GET /api/health`：服务和依赖就绪状态。
- `POST /api/chat`：文本消息 -> 结构化回复（带 session_id）。
- `GET /api/conversations`；`GET /api/conversations/{id}/messages`；`DELETE /api/conversations/{id}`。
- `GET /api/memories`；`POST /api/memories`；`PATCH /api/memories/{id}`；`DELETE /api/memories/{id}`。
- `POST /api/audio/transcribe`；`POST /api/audio/synthesize`（可配置，输出带媒体类型）。
- `GET/PATCH /api/pet/settings`；`GET /api/pet/state`。
- `GET /api/devices`：区分 simulator、PCMic、ESP32 实机。
- `GET /api/diagnostics`：不包含密钥的诊断信息。

先检查旧 API 的命名兼容性，尽量避免破坏原有前端调用。

### 5.2 统一事件模型（示例，不等于小智官方协议）

```json
{
  "version": 1,
  "event_id": "uuid",
  "timestamp": "2026-11-05T08:30:00+09:00",
  "device_id": "pixelpet-sim-001",
  "type": "touch.tap",
  "payload": { "duration_ms": 132 }
}
```

事件分类：`touch.*`、`pet.state`、`pet.emotion`、`audio.record_start`、`audio.record_stop`、`audio.speak_start`、`audio.speak_end`、`haptic.pattern`、`device.connected`、`device.disconnected`、`device.error`、`clock.tick`。

状态机要校验合法转移，例如未连接时不可直接进入真实 `SPEAKING`，录音/播放互斥。利用 FSM 单测覆盖触摸连击、长按、超时、断线与重复事件。

## 6. 工程质量与安全要求

- 完整项目文件和迁移脚本，拒绝仅有伪代码、空函数、TODO 作为已完成功能。
- `.env` 必须 ignore，`README` 提供 `env` 模板；应用启动时检查必要设置，不得显示真实密钥。
- DB 使用事务、唯一约束、索引；避免重复保存；备份文件不进 Git；注意 Windows 路径及多进程文件锁。
- 不在浏览器 localStorage 中保存 DeepSeek API Key；前端所有 AI 请求走 PC 端。
- 输入大小、音频长度、文件类型、WS 数据长度限制，防止错误/过大的音频导致崩溃。
- 完善 API 错误模型：未授权、网络错误、超时、ASR/TTS 未就绪、模型输出格式错误等。
- 记录耗时统计：ASR、LLM 首 token、TTS、端到端（不要求提前实现低延迟实时流式）。
- 网络服务默认只监听 `127.0.0.1`，如需 ESP32 接入绑定 `0.0.0.0`，必须额外配置鉴权与 Windows 防火墙局域网规则，禁止公网端口暴露。
- 语音/聊天隐私提示明确区分本地 SQLite 和发往第三方模型的内容；默认不长期存原始录音。
- 批量测试不应消耗真实付费 API；Mock 测试为默认，单独设置环境开关才允许用真实密钥做小量 smoke test。
- 加 `README.md`、`docs/architecture.md`、`docs/architecture_decision.md`、`docs/deployment_windows.md`、`docs/api.md`、`docs/hardware_pending.md`、`docs/hardware_acceptance.md`、`docs/test_report.md`。

## 7. 执行顺序：一次交付，但按依赖拓扑实现

> “一次做完”是目标，不是让尚未稳定的上游逻辑同时改动。请连续完成各阶段，遇到硬件门槛后将硬件事项标为待验证并继续其他工作。

| 批次 | 任务 | 可在 PC 完成 | 验收 |
| --- | --- | --- | --- |
| 0 | 基线检查、Git checkpoint、读项目、跑原测试 | 是 | 原测试报告/现状表 |
| 1 | DeepSeekProvider + 真实聊天 + 失败降级 | 是 | 真 API 小量 smoke + Mock 全测 |
| 2 | 历史消息、跨会话 SQLite 和记忆检索/管理 | 是 | 重启仍能召回；删除不命中 |
| 3 | 角色/情绪/FSM/240×240 动画 | 是 | E2E 按对话切表情 |
| 4 | PC 麦克风 ASR、PC 扬声器 TTS | 是 | 从说中文到听回答的 PC 闭环 |
| 5 | TTP223/Haptic 模拟器、配置与主动问候 | 是 | 交互事件、提醒、静音可复现 |
| 6 | 设备事件与 WebSocket mock client | 是 | 重连/消息/状态单测 |
| 7 | 小智适配策略、独立 vendor 实验分支 | 部分 | 协议兼容测试说明、可运行模拟测试 |
| 8 | ESP-IDF 设备端板级驱动框架与编译 | 部分 | 能编译则附编译日志，否则真实环境阻塞说明 |
| 9 | 整体验收、README、文档、QA | 是 | 可复现的启动与测试流程 |
| H | 真实屏幕/音频/触摸/马达/BLE 联调 | 否 | HW_PENDING，待器件到货 |

## 8. 必须跑的测试矩阵

1. 启动/停止、浏览器加载、原有第一阶段全部测试。
2. DeepSeek Mock 模式聊天、真实 API 极少量 smoke、超时/429/401/空响应/格式错误。
3. 多轮对话、跨会话上下文、SQLite 重启持久化、删除/导出、隐私清理。
4. 记忆提取、去重、冲突、时间筛选、相关性、无记忆时诚实回答。
5. 录音权限拒绝、空音频、最大长度、ASR 未安装、TTS 降级、无法播放。
6. 动画所有状态、切换与连续多次切换、画布严格240×240、资源导出校验。
7. Touch single/double/long、长按取消、抖动、重复事件、录音与震动互斥。
8. 网络断线、WebSocket 重连、device heartbeat、状态同步、服务端重启恢复。
9. 启用免打扰、关闭主动问候、错过提醒、重启后提醒去重。
10. 确保 API Key 不出现在 git diff、前端 bundle、日志和样例响应。
11. 硬件驱动仅进行静态/构建/模拟测试，实际供电、时序、音频、屏幕和马达列在 HW_PENDING。

**输出证据：** 保存测试命令、执行结果摘要、失败用例与修复结果；禁止只写“已全部测试通过”而无记录。

## 9. 交付物与最终回复格式

必须在 `D:\PixelPet` 输出：

- 真实可运行后端代码（AI、记忆、ASR/TTS 可切换实现、配置、API）。
- 可运行 PC 前端像素模拟器（支持真实聊天、真实 PC 音频、动画和模拟触觉）。
- SQLite 迁移、示例数据/测试夹具和备份脚本。
- WebSocket/设备抽象、模拟设备客户端、协议 schema。
- ESP32-S3 板级配置/驱动框架及单元测试或构建说明。
- 一键启动脚本（Windows PowerShell/.bat）、一键测试脚本、`env` 模板。
- 上述 `docs/` 中的完整文档。
- 需要实际器件才能验证的 `HW_PENDING` 清单及到货后的操作顺序。

Codex 最终回复须包含：

1. **完成情况表：DONE / PARTIAL / HW_PENDING / BLOCKED**。
2. 修改文件清单（按功能分组），不得罗列无意义的数百个路径。
3. Windows 一键启动命令和浏览器地址。
4. 运行了哪些测试、各自通过/失败数量、真实日志路径。
5. DeepSeek 真实 API 是否实际测试；若未测试，要注明原因。
6. PC 麦克风/扬声器真实语音是否测试；若未测试，要注明原因。
7. 当前仍需用户完成的**最少步骤**（如填写 `.env`，安装驱动/允许麦克风）。
8. 硬件到货后第一天先测什么、再测什么；不要宣称未实测的固件已经可用于生产。

## 10. 到货后的硬件联调顺序（现在先写好文档）

1. 核对板子模组 N16R8、GPIO 丝印、3.3V/5V、电源路径、USB 烧录。
2. ST7789 单独供电点亮：确认 BL、屏幕方向、RGB/BGR、偏移、色彩及帧率。
3. INMP441 单独录制，检查 16/24/32bit 对齐、数据噪声、采样率；保存测试音频。
4. MAX98357A 单独播放低音量 WAV/测试音，确认扬声器接法与电源电流。
5. TTP223 数字输入测试短按/长按/防抖；无法满足触摸外形时考虑铜箔位置。
6. 震动马达先校验驱动输入阈值、供电与电流，再实现 PWM 和不同节奏；验证马达不会造成音频干扰或设备复位。
7. 分别打开 Wi-Fi、BLE，再与所有模块同时运行；检测 GPIO 冲突、电压跌落、内存与任务拥塞。
8. ESP32-S3 连接 PC 本地服务，验证触摸 -> 录音 -> ASR -> DeepSeek -> 记忆 -> TTS -> 喇叭 -> 表情全过程。
9. 电源、稳定性、长期运行测试；最后再考虑3D打印外壳。

## 11. 参考资料（以官方资料及所锁定源码版本为准）

- DeepSeek 官方 API 入门：<https://api-docs.deepseek.com/>
- DeepSeek 思考模式：<https://api-docs.deepseek.com/guides/thinking_mode/>
- 小智 ESP32 官方固件：<https://github.com/78/xiaozhi-esp32>
- 小智自定义板指南：<https://github.com/78/xiaozhi-esp32/blob/main/docs/custom-board.md>
- 小智 Python 服务端：<https://github.com/xinnan-tech/xiaozhi-esp32-server>
- 小智服务端部署说明：<https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/docs/Deployment.md>
- 乐鑫 ESP32-S3 触摸引脚与硬件设计：<https://documentation.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html>
- 乐鑫 ESP32-S3 I2S 驱动：<https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html>

---

## 12. 开始执行（给 Codex 的最后指令）

**立即打开 `D:\PixelPet`，读取现有代码并执行批次 0 至批次 9。不要只给规划；尽可能直接写、修、跑和验证真实软件。硬件未到的批次 H 只生成驱动框架、模拟测试和待验证文档。**

如果发现现有代码已经完成其中一部分，验证后标记 DONE，避免重复实现；如果遇到小智兼容、音频依赖或硬件验证阻塞，保留隔离的 Adapter 和充分的 Mock 测试，写清阻塞原因并继续其它模块。
