# 小星 V1 自然语音优化

## 原实现与备份

原默认链路是 Windows SAPI 在后端生成 WAV，前端 Audio 播放；浏览器 speechSynthesis 是可选方案，原先没有 Edge Provider。SAPI 传统系统音色的自然度有限，原文本直接朗读 Markdown，缺少统一文本清理与取消控制。原有 22050Hz 单声道 WAV 的头和解码有效，没有证据表明机械感来自错误采样率或变速。

改动前源代码：`output/tts-before-natural/source-before.zip`；数据库快照：`output/tts-before-natural/database-before.sqlite3`。备份不含 .env。需要回退时先停止服务，将源代码解压至单独目录核对后覆盖；只有明确需要恢复旧数据时才恢复数据库，以免丢失新增聊天。不覆盖当前 .env。

## 新链路

DeepSeek 回复 → Markdown/中文标点清理 → 有界情绪参数 → TTSProvider → Edge MP3 → PyAV 实际解码/重采样 → 单声道 PCM16 WAV → 统一前端播放器。

- EdgeTTSProvider、MockTTSProvider 和离线 SAPI 已实现；AzureSpeechProvider、CustomTTSProvider 为未配置插槽，不会调用收费接口。
- 默认 `zh-CN-XiaoyiNeural`，rate `+0%`、pitch `+0Hz`、volume `+0%`。语速限制 ±20%，音调只提供小范围手动调整，默认及情绪不自动升调。音量只减小、不正向增益。
- 晓伊、晓晓、云希已真实联网生成并由浏览器播放完成。晓梦不在当前实测在线目录中，显示禁用，不用其他声音冒充。目录证据：`output/edge-voice-catalogue.json`。
- 同句试听：「你好呀，我是小星！今天也很开心见到你，嘿嘿，要不要陪我聊聊天？」
- happy +4%、shy −3%、sad −5%、curious +1%、sleepy −7%、surprised +5%；normal/angry/thinking 不附加语速。最终仍限制在 ±20%。这是轻微语速提示，不是 Edge 情绪风格或任意 SSML 支持。
- 保留数字、单位、负号和中文标点；删除视觉 Markdown、链接目标、装饰 emoji；代码块提示查看屏幕。按整句/分句限制 2000 字，不逐字合成、不增加口头禅。界面保留完整回复。详见 tts_text_audio.md。
- Edge 网络请求限时、最多重试一次，取消向异步生成任务传播。普通回复允许明确标示 SAPI 降级；试听禁止替代音色。错误后可再次点击试听。

## 界面与状态

主页面右上「设置」→「语音输出」Edge →「声音」→「试听当前声音」。声音控制自动保存；恢复默认回到晓伊和零偏移。比较页 `/voice-test` 展示实际音色、Provider、生成耗时、参数和状态。修改音色后下一次回复使用新设置。

状态为 IDLE、GENERATING_AUDIO、PLAYING_AUDIO、STOPPING_AUDIO、AUDIO_ERROR。合成时 THINKING，真正开始播放才 SPEAKING；嘴巴按实际播放时间变化，不声称测量了音频能量。结束/停止恢复 IDLE，错误恢复动画并显示提示。新播放替换旧任务，取消 fetch，释放 Audio 与 object URL，迟到的旧响应不播放。前端 playbackRate 固定 1，避免二次变速。

## 音频与设备边界

PC 默认 WAV：24000Hz、16bit、单声道；可显式选 16000Hz。响应头声明真实格式、时长、峰值、饱和比例、参数和是否降级；明显饱和拒绝播放。源采样率经过正常重采样，不修改文件头冒充另一采样率。峰值检查不能证明主观音质，也不能检测所有源音频失真。

`output_format=device_pcm` 返回裸 PCM16 little-endian，明确 16/24kHz、单声道；`device_wav` 返回带头 WAV。设备必须按声明参数初始化 I2S。尚未实现小智 Opus 网关，不假定 ESP32 可直接播放 MP3。GPIO 映射未改，MAX98357A、8Ω 喇叭、电气/实机音质全为 **HW_PENDING**。

## 修改文件

- 后端：backend/speech/providers.py、text.py、conversion.py、service.py；backend/api/audio.py；backend/preferences/service.py；backend/main.py。
- 前端：frontend/index.html、css/v1.css、js/audio-player.js、runtime.js、chat.js、pet.js；frontend/voice-test.html、js/voice-test.js。
- 验证：tests/test_natural_tts.py、test_natural_tts_api.py、test_tts_processing.py、audio_player_check.cjs；scripts/browser_voice_check.js、browser_voice_defaults_check.js、browser_voice_state_check.js、verify_natural_tts.py。
- 依赖/文档：requirements.txt、README.md、docs/speech.md、tts_text_audio.md、natural_tts_report.md。

## 验证结果

详细自动化与真实联网结果见 `output/natural-voice/report.json`、浏览器报告和本节后续记录。原有 DeepSeek、SQLite 记忆与硬件模拟测试均保留。没有进行 ESP32 实机测试；电脑物理扬声器听感需要主人试听判断，不将浏览器播放完成当作听感评分。

- 全部 Python 测试 **188 passed**（22.58s），包含原有 AI/长期记忆、声音设置重启持久化、转换、不可用音色、网络故障/降级、超时与客户端断开取消；日志 `output/natural-voice/pytest-final.log`。
- Node 播放器契约测试通过，覆盖重复播放、迟到任务、停止、错误/重试、资源释放及无未处理 Promise rejection；三个前端脚本语法检查通过。`pip check` 无依赖冲突。
- 真实同句 Edge 合成：晓伊 6.840s/328364字节、晓晓 6.888s/330668字节、云希 6.840s/328364字节；均 PCM16/24000Hz/单声道、无降级，饱和采样比例 0。可直接播放 `output/natural-voice/*.wav`。
- 真实 DeepSeek `deepseek-flash` → 中文回复 → Edge 晓伊 WAV 217772字节成功，测试数据留在 tmp 隔离数据库；报告包含实际回复与情绪。
- 浏览器首次验收 24/24 通过，实际三音色生成、播放完成、停止与连续播放、错误重试、自动保存、移动端布局均验证；另修复旧 SAPI 空音色设置的升级兼容问题，回归 3/3。桌面/移动截图在 `output/playwright/voice-test-*.png`。Edge 在线网络仍可能暂时不可用，不能承诺离线使用在线声音。
- 最新浏览器在线复跑完成 13 项后，Edge 连接重置导致两次请求 503，后续在线部分未完成；这次失败保留在 `output/playwright/browser-voice-check-latest-failure.json`，不算全部通过。绕过 FastAPI 的直接 Edge 调用也复现 `ClientConnectorError/ConnectionResetError`，随后独立浏览器探测恢复 200（2015ms），见 `browser-voice-after-cancel-probe.json`。不将临时网络失败掩盖为成功。
- 最后修复后的独立浏览器回归：旧 SAPI/Mock/Edge 默认音色 3/3；合成 THINKING、播放前错误/取消回 IDLE 3/3。报告分别为 `browser-voice-defaults-check.json`、`browser-voice-state-check.json`。初次 24 项成功记录来自当时工具结果的整理，明确标注其来源在 `browser-voice-check-initial-observed.json`；最新完整脚本加入了三个状态断言，在线部分仍受上述网络波动影响。
