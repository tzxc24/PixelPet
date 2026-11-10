# PixelPet V1 测试与交付报告

日期：2026-11-05。代码位于 D:\PixelPet；没有根Git仓库，变更前以 output/v1-baseline 保存源码/SQLite快照，未复制.env。

## 结果矩阵

| 模块 | 状态 | 实际证据 |
| --- | --- | --- |
| 原有AI/SQLite/模拟器及新增后端 | DONE | 155项Pytest通过，21.56秒；保留原27项第一阶段用例 |
| 原生ESP32-S3编译 | DONE | ESP-IDF v6.1，退出0，250192字节固件；根代理再次执行build.ps1通过 |
| C++主机检查 | DONE | 状态核心、禁用驱动、并发录音/马达互锁3项编译与断言通过 |
| 引脚校验 | DONE | 28项冲突/保留/禁用/冻结/头文件一致性用例通过 |
| 设备业务协议 | DONE | 31项FSM/WS/鉴权测试；两次连接、hello、音频控制、响应、断线重连通过 |
| 聊天/记忆/原8态浏览器回归 | DONE | 40项真实浏览器检查，无脚本异常 |
| 真实WAV与本地ASR软件链路 | DONE | 19项浏览器检查，生成音源→WebM录制→Whisper→真实DeepSeek→SAPI→浏览器播放完成 |
| 真实人声麦克风和物理扬声器听感 | PARTIAL | 未由真人收音/试听验证，不用合成音源冒充 |
| 小智原生Opus网关、完整端侧业务/无线 | PARTIAL | 固定上游SHA与网关B方案，当前只有业务JSON模拟，不宣称兼容原生设备 |
| 所有硬件接线/电源/时序/音质/触摸/震动/无线 | HW_PENDING | 无器件、未烧录，全部电气门控false |

155项总数包含上述Python分类，不应将28/31再次加到155上。

## 命令与日志

- `.venv\Scripts\python.exe -m pytest -q --tb=short`：output/v1-pytest-final.log。
- `powershell -ExecutionPolicy Bypass -File firmware\build.ps1`：output/firmware-rebuild.log；完整首次原生编译和最终结果见 firmware-idf-build-final.log / .exit，首次编译错误日志保留。
- 主机编译/断言：output/firmware-host-report.txt；编译命令见 firmware/pixelpet_s3/README.md。
- `scripts/generate_pinmap.py --check`：冻结映射及头文件一致性通过。
- `scripts/mock_device.py`：两轮JSON业务连接生命周期通过，另有 output/mock-device-report.txt。
- `scripts/backup.py`：真实SQLite在线备份到 output/backups，未复制.env。
- JavaScript node --check、Python compileall通过；uv pip check确认58个安装包兼容。
- 浏览器：output/playwright/v1-browser-results.json（19）与 v1-text-regression-results.json（40）；原始日志同目录。
- 真实云端：output/v1-live-smoke.json，mode=deepseek，含实际首token/总耗时；另有隔离库重启跨会话验证 live-llm-verification.json。
- 本地语音：output/speech-loopback-verification.json。base CPU约1秒识别约6秒合成音频，存在“桌宠”同音字误识，不将此结果写成逐字准确。

## 验证范围

真实SAPI产生22050Hz单声道16-bit PCM WAV；浏览器Audio实际解码、currentTime前进且ended完成。测试音源通过WebAudio生成/送入MediaRecorder，不是真实麦克风；没有由人确认声音从哪只扬声器发出或音质如何。权限拒绝、延迟授权、取消ASR不继续发消息、停止播放均有浏览器检查。

深度模型真实调用使用用户已配置的后端密钥，默认批量测试不消耗云端API。测试数据为隔离库或明确验收会话；原用户画像/记忆保留。完整密钥不出现在前端、源码或报告中，最终另做全值扫描。

本机仍是单主人应用，不是账户多租户。局域网显式Host与Bearer保护已实现并测试，尚未实际打开防火墙或与ESP32连通。主动问候默认关闭，定时通知只在服务与页面运行时领取，不承诺关机通知。RGB565导出已验证字节长度与测试颜色，真实屏幕字节序/RGB-BGR/旋转/偏移未验证。

## 本次关键修复

录音/播放互斥、取消代际检查、过期权限结果释放、59秒上限；完成AI回复后刷新故障不覆盖成功文本；会话切换失败恢复原选择；记忆否定/确认语义；实际分块body限制、Host/Origin与WS鉴权；保存模型重启恢复；屏幕DMA完成栅栏、马达与录音并发互锁。

## 到货后

依 hardware_wiring.md、pinout_validation.md 和 hardware_acceptance.md，先核对PCB/电源，再逐模块独立上电。BL、字库CS-F、马达电源/门限及功放SD/MODE未确认前保持不接/禁用。先验证屏幕和低风险触摸，再分别验证录音/播放与马达，最后联调，保存照片、测量及日期后才能升级 VERIFIED。
