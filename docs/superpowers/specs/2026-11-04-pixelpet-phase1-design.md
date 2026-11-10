# PixelPet 第一阶段设计

日期：2026-11-04
项目位置：D:\PixelPet
状态：待用户确认；尚未实现或测试。

## 范围与方案

本阶段交付可在 Windows 上运行的 PC 项目骨架和浏览器桌宠模拟器。

推荐 FastAPI 同时提供静态页面与 API：一个进程、同源访问，启动步骤少，便于后续加入 AI 和设备接口。
另两个选项为前后端独立服务（开发配置更多）和原生桌面应用（增加打包及平台依赖）。本阶段采用推荐方案。

## 后端与持久化

使用 Python 3.10 兼容代码、FastAPI、Uvicorn、SQLAlchemy 和 SQLite。
应用启动时初始化数据库；预建 user_profile、conversations、messages、memories、pet_settings 五类表，不实现自动记忆提取或云端 AI 调用。
数据库与运行产物位于 output，临时文件位于 tmp。路径从项目根目录解析，不依赖启动时所在目录。
GET /api/health 检查服务及数据库连通性；数据库不可用时返回明确失败状态。
GET /api/pet/state 返回当前模拟状态；POST /api/simulator/events 接受受限的硬件模拟事件，返回更新后的状态。
第一阶段模拟器面向单个本机用户，状态驻留进程内，不宣称具备多用户隔离或设备认证。

## 浏览器模拟器

使用原生 HTML、CSS、JavaScript 和 Canvas，浅色背景，居中显示 240×240 像素画布，采用清晰整数像素绘制。
角色“小星”采用星形轮廓、表情眼睛及小腮红，具有呼吸、眨眼等实际动画。
提供八种本地预览状态：IDLE、HAPPY、LISTENING、THINKING、SPEAKING、SHY、SLEEP、SURPRISED。
显示本机时间、状态和情绪；提供触摸、录音开始/结束、语音播放及 Wi-Fi/BLE 连接模拟按钮。
聊天区域只提供明确标注的演示反馈与清空功能；不把演示反馈描述成 AI，也不声称已有跨会话记忆。
按钮事件通过模拟 API 获取反馈，网络错误可见；前端动画循环不依赖 API 请求持续运行。
录音和播放不访问真实麦克风、音频硬件或系统权限。

## 模块边界与未来扩展

backend 下划分 api、core、database、character、hardware；frontend 保存页面、样式和动画脚本。
HardwareSimulator 通过事件接口管理状态，避免将 GPIO、I2S 或具体引脚引入业务逻辑。
AI、记忆检索、语音、小智协议和 BLE 配置的真实实现留到后续阶段；本阶段不声称兼容小智线协议。
不安装完整小智服务端，不接入 PowerMem，不接云端模型。

## 运行与验收

提供 requirements.txt、.env.example、.gitignore、README 和 PowerShell 启动脚本。
README 包含 Python 环境、安装依赖、启动、测试命令和预期界面。
配置通过环境变量读取；示例不包含真实密钥；本阶段无需 API Key。
使用 Pytest 验证数据库初始化、健康检查、状态获取、模拟事件映射、非法事件拒绝以及主页可访问。
以实际服务验证页面加载和动画交互；若无法进行浏览器验证，明确列出未验证项。
不执行真实 GPIO、麦克风、功放操作，不覆盖任何已有文件。

## 设计自检

范围限于第一阶段；模拟与真实功能已明确区分；数据库初始化不等于长期记忆功能。
运行产物与临时文件均位于 D 盘项目内；后续功能通过模块接口扩展。
