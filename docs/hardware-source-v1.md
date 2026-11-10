# PixelPet V1.0 — ESP32-S3 N16R8 接线与 GPIO 冻结草案

版本：V1.0（2026-11-05）  
状态：**SOFTWARE_PINMAP_FROZEN / PHYSICAL_PINOUT_UNVERIFIED**  
适用：用户拟购第三方 ESP32-S3 N16R8 核心板；尚未取得确切板卡 PCB 引脚图，元件尚未到货。

> **总原则：**把以下映射先写进集中配置和模拟器；可以写/编译固件，但不能宣称物理接线已经验证。收到开发板正反面引脚照片、ST7789 电源/背光参数、震动模块供电规格后，复核再真实接线。切忌靠猜测连接电源或 BL 引脚。

## 1. 全部模块与 GPIO 分配（首选、独立 I2S）

| 模块 | 模块引脚 | ESP32-S3 | 备注 |
| --- | --- | --- | --- |
| INMP441 数字麦克风 | SCK | GPIO4 | I2S RX bit clock |
| INMP441 | WS | GPIO5 | I2S RX word select |
| INMP441 | SD | GPIO6 | I2S RX data in |
| MAX98357A 数字功放 | BCLK | GPIO7 | I2S TX bit clock |
| MAX98357A | LRC / WS | GPIO8 | I2S TX word select |
| MAX98357A | DIN | GPIO9 | I2S TX data out |
| ST7789 1.33英寸 240×240 SPI TFT | SCL (SCK) | GPIO14 | **SPI时钟，不是I2C时钟** |
| ST7789 | SI (MOSI) | GPIO15 | SPI写数据 |
| ST7789 | RST | GPIO16 | 复位 |
| ST7789 | DC | GPIO17 | 数据/命令 |
| ST7789 | CS | GPIO18 | TFT片选 |
| TTP223 电容触摸 | SIG / OUT | GPIO13 | 默认按高电平触摸，实际模块需核实 |
| MOS驱动震动马达一体模块 | IN / SIG | GPIO21 | 高电平触发；**驱动模块供电/电平需核实** |
| ST7789 背光（仅预留） | BL | GPIO10（预留，不连） | **不得默认直连 GPIO**，明确有逻辑/PWM输入或外置MOS驱动后才启用 |

**计数：** 必用 GPIO 13 根，另预留 BL GPIO10 1 根。将 GPIO11 / GPIO12 预留给未来 I2C 传感器；GPIO1 / GPIO2 留作未来ADC/按键，具体待实物确认。

### 不用或谨慎使用的 GPIO

- GPIO0 / GPIO3 / GPIO45 / GPIO46：启动配置（strapping），本项目不分配普通外设。
- GPIO19 / GPIO20：ESP32-S3 原生 USB D- / D+，保留给烧录和调试。
- GPIO35 / GPIO36 / GPIO37：N16R8 Octal PSRAM 相关，不能当普通空闲 GPIO 使用。
- GPIO26～34：Flash/PSRAM相关或没有引出，不用于本项目。
- GPIO43 / GPIO44：预留给板载或外部 UART 串口调试（取决于开发板）。
- GPIO39～42：先保留，避免 JTAG 调试冲突。
- GPIO47 / GPIO48：先保留，部分开发板 GPIO48 与板载 RGB LED 有关。

官方参考：
- Espressif DevKitC-1 引脚表：https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html
- Espressif S3 启动配置引脚：https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html
- Espressif I2S 标准模式：https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html

## 2. 按模块逐线接线

### 2.1 INMP441（7线）

| INMP441 | 连接 |
| --- | --- |
| VDD | ESP32-S3 3V3，绝不可上5V |
| GND | 公共GND |
| SCK | GPIO4 |
| WS | GPIO5 |
| SD | GPIO6 |
| L/R | GND，选左声道 |

推荐初始化 I2S RX 为标准 I2S，16kHz、32-bit slot，再正确将 INMP441 的有符号24-bit采样缩放为 PCM16；注意左声道和实际字节序，不可直接假定16-bit原始数据。

### 2.2 MAX98357A + 喇叭

| MAX98357A | 连接 |
| --- | --- |
| VIN / VCC | 优先开发板 USB 5V 引出（仅在确认该板提供5V且供电容量足够时） |
| GND | 公共GND |
| BCLK | GPIO7 |
| LRC / WS | GPIO8 |
| DIN | GPIO9 |
| SD / MODE | **根据实际模块板载电阻和原理图确定**，不能盲目接地或假设悬空能播放 |
| GAIN | 先保留模块默认增益 |
| SPK+ | 扬声器正端 |
| SPK- | 扬声器负端，**不能接地** |

建议喇叭8Ω 2～3W，5V 供电下放大器实际输出功率随负载与音量变化。小音量先测；功放旁加足够去耦，模块上已有去耦时核对即可。

### 2.3 ST7789（用户发来的10针带字库版本）

| 脚号 | 符号 | 连接及状态 |
| ---: | --- | --- |
| 1 | GND | 公共GND |
| 2 | VCC | **待确认模块工作电压**；若可3.3V供电，优先3V3 |
| 3 | SCL | GPIO14（SPI SCLK） |
| 4 | SI | GPIO15（SPI MOSI） |
| 5 | SO | 首版不接（不读屏或字库） |
| 6 | RST | GPIO16 |
| 7 | DC | GPIO17 |
| 8 | CS | GPIO18 |
| 9 | CS-F | 字库芯片片选；不用字库时必须可靠保持非选中（通常为高电平），核对原理图与拉高要求，不可任意悬空 |
| 10 | BL | **背光电路未确认，暂不接**；确认限流和控制方式后再接电源或通过外部MOS驱动，GPIO10仅为预留PWM控制 |

显示设置初版：240×240、RGB565、ST7789，SPI写模式；旋转、MADCTL、颜色顺序和显示偏移待实机检验。字库芯片不是 PixelPet 字体依赖，中文和像素资源由主控端完成。

### 2.4 TTP223 触摸

| TTP223 | 连接 |
| --- | --- |
| VCC | 3V3 |
| GND | 公共GND |
| OUT / SIG | GPIO13 |

启用输入去抖；首版采用点动/非锁存；GPIO 输入高电平表示触摸是**候选配置**，以实测模块状态为准。固件支持短触摸、连续触摸、长按说话及松手停止录音。声音录制和震动之间加入延迟，降低麦克风机械噪声。

### 2.5 MOS 驱动震动马达一体模块

| 模块 | 连接 |
| --- | --- |
| IN / SIG | GPIO21 |
| GND | 公共GND |
| VCC | **型号参数待确认：3V/3.3V/5V，不可猜测** |

商品图片描述为 MOS 高电平触发，低电平截止，支持 PWM；但是没有给工作电压与3.3V输入高电平阈值。购买前要确认是否直接接受 ESP32-S3 的3.3V输入，是否有电机续流保护。软件上 GPIO21 上电尽快初始化为 LOW；建议模块控制输入加适当下拉，防止上电误震。**绝不让 ESP32 GPIO 直接向电机供电**。

## 3. 供电与布线安全

- 第一版 USB-C 5V 给开发板供电（用有数据传输能力的线）。
- 3V3 rail 给 INMP441、TTP223，ST7789仅在供电额定值确认后连接。USB 5V rail 给功放需确认开发板实际引出和USB供电能力。
- 马达按商家额定电压供电；功放与马达的瞬态电流可能引起重启，不要默认3V3板载稳压器有足够余量。
- 全部外设共地；5V模块逻辑接口必须确认可由3.3V GPIO驱动，且不能往 ESP32 GPIO 回灌5V。
- ST7789 BL 与字库 CS-F **是当前两处电路待确认项**，切勿凭用户的引脚定义表把它们直接接在3.3V或GPIO10上。
- 未接电源时先核对VCC/GND极性、无短路；首次上电一次只加一个模块。

## 4. 固件原则：ESP-IDF（基于小智参考）

1. Target `esp32s3`，启用16MB Flash、8MB Octal PSRAM（通过实物硬件/启动信息验证，不能仅凭商品标题）。
2. 所有引脚定义只存在一个中央文件：`firmware/main/board/pixelpet_pin_config.h`，禁止在各驱动中散落数字 GPIO。
3. 实现 `board_init()`、`display_init()`、`microphone_init()`、`speaker_init()`、`touch_init()`、`haptic_init()`；硬件未到货时可用 Mock/编译开关。
4. I2S RX 和 TX 初期按**独立BCLK/WS**（2套时钟、6根线）配置，不强行优化成共享时钟；如用独立 I2S 控制器/句柄，遵循当前 ESP-IDF 文档的资源分配规则。
5. 显示用单独队列/任务接收 `IDLE / HAPPY / LISTENING / THINKING / SPEAKING / SHY / SLEEP / SURPRISED`；优先以小图帧/分区刷新的方式降低SPI刷屏开销。
6. 音频链路：INMP441 -> ESP32 PCM -> 小智兼容音频传输（后续校验协议） -> PC服务端 -> DeepSeek LLM + ASR/TTS服务 -> ESP32 -> MAX98357A。DeepSeek模型本身不能直接承担麦克风采样、ASR和TTS。
7. 触摸事件 `TOUCH_TAP / TOUCH_DOUBLE / TOUCH_HOLD_START / TOUCH_RELEASE`；震动事件 `HAPTIC_SHORT / HAPTIC_DOUBLE / HAPTIC_LONG`；录音期间尽量禁止震动。
8. Wi-Fi、BLE不需要额外GPIO；BLE尽量仅在手机配置/配网时启用，减轻同频无线并发压力。
9. 明确区分编译通过、软件模拟通过、实机通过；真实硬件未到货标记 `HW_PENDING`。
10. 小智原生协议不等同于自定义 JSON WebSocket；若复用小智服务端，应做独立 `xiaozhi_adapter`，不要擅自修改原有音频协议。

## 5. 引脚核验计划（硬件到货后）

- [ ] 拍摄开发板正反面，确认商家 PCB GPIO丝印 / 引脚排列 / USB供电引脚 / 电源芯片规格。
- [ ] 确认芯片实际是 `ESP32-S3 N16R8` 且 PSRAM/Flash容量识别成功。
- [ ] 商家确认ST7789 VCC范围、BL是否自带限流、CS-F是否有上拉及模块 SPI 电平。
- [ ] 商家确认震动模块工作电压、GPIO 3.3V输入可驱动、上电默认状态及保护元件。
- [ ] 检查功放 SD/MODE 管脚默认电路和增益设置。
- [ ] 先单独点亮ST7789（背光接法确认后），再测试Touch和Haptic。
- [ ] 再分开测试 INMP441录音和MAX98357A播放，然后全链路联调。
- [ ] 正式接线后更新版本号 `V1.1 VERIFIED` 与实际引脚照片/测试记录。

## 6. 给 Codex 的执行范围

在现有 `D:\PixelPet` 工程内：

1. 检查现有 `firmware/` 或 ESP-IDF 目录，不覆盖既有业务代码和现有 pin map；如果存在冲突，先导出冲突对比，并在单一配置文件统一变更。
2. 导入附带 `pixelpet_pin_config.h` / `pinmap.json`，以 JSON 为单一工程配置源或建立一致性校验。
3. 对接现有 PC 模拟器：GPIO事件通过 `hardware_adapter` 统一转换，模拟器不直接依赖 ESP-IDF。
4. 只生成已核实电气条件下的驱动功能；未核实的 BL、字库片选、马达供电以 `TODO(HW_PENDING)` 显式阻止危险自动启用。
5. 增加引脚冲突与禁用GPIO自动检查，测试不能只检查表格，应能检测重复复用、strapping、USB和PSRAM引脚。
6. 尝试安装/使用 ESP-IDF 工具链并编译 `esp32s3` target；若无法安装则保留构建文档并注明未编译原因，不能声称通过。
7. 生成 `docs/hardware_wiring.md`、`docs/pinout_validation.md`、`firmware/main/board/pixelpet_pin_config.h` 和硬件验收清单。

**DoD**：PC既有功能不退化；所有 GPIO 定义唯一；固件软件测试完成或记录实际阻塞；设备尚未到货且电气待确认项绝不被标为实机可用。
