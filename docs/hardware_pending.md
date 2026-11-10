# Hardware pending register

Everything below is HW_PENDING; no hardware has arrived or been measured. Supplier URLs were not supplied: each purchase-page link, order SKU and front/back photo must be attached after receipt. Software source references are not supplier evidence.

| Module | Evidence needed / unresolved |
| --- | --- |
| ESP32-S3 N16R8 | Module and board revision photos, manufacturer pin map/schematic, flash/PSRAM wiring, USB and strapping usage; supply rail measurements |
| ST7789 240×240 10-pin | Exact module page and pin labels; BL resistor/driver and allowed voltage; CS-F/font chip idle requirements; SPI timing, rotation, RGB/BGR and offsets |
| INMP441 | L/R selection, 3.3V supply, clock/data alignment, slot width, noise floor and sample rate |
| MAX98357A + 8Ω speaker | Board supply voltage, gain/shutdown configuration, BCLK/WS acceptance, current peaks; speaker goes between amplifier outputs, not ground |
| TTP223 | Supply/IO voltage, active polarity, momentary/latching solder mode, enclosure sensitivity and debounce |
| MOS motor module | Input high threshold at 3.3V, supply range/current, flyback/protection, PWM compatibility, startup current and acoustic coupling |
| Wi-Fi / BLE | LAN auth, pairing security, provisioning persistence, reconnect/backoff and long-run stability |

V1.0 软件映射现已从用户正式文件统一到 hardware/pinmap.json，生成 firmware/main/board/pixelpet_pin_config.h。它指定13路计划信号，但 hardware_enabled=false；BL与CS-F=-1，GPIO10只预留。GPIO冲突、保留、USB/启动/PSRAM和一致性检查已实现。软件门控不等于电气验证。

ESP-IDF v6.1 已在D盘安装，实际 esp32s3 编译退出0，三项C++ host断言通过。SPI/I2S/触摸/马达驱动函数已加入安全禁用门控，尚未烧录或实机测试；Wi-Fi/BLE、端侧动画任务和小智原生网关未完成集成。详见 firmware_build.md。
