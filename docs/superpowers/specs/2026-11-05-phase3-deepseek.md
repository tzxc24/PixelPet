# DeepSeek 集成记录

用户在第二阶段执行期间进一步指定第三阶段：DeepSeek 官方、deepseek-flash、thinking disabled、OpenAI Python SDK，并授权本地保存密钥和实际测试。此要求作为当前项目的追加实施范围，不替代持久会话和长期记忆目标。

实现选择：独立 DeepSeekProvider 使用 AsyncOpenAI，协议统一为 complete/stream/close。非流式先打通，随后保留现有 SSE 服务层；SDK 重试关闭以控制总超时。JSON Output 提示词含合法 json 示例，并将有界助手历史重新序列化为 JSON；输出通过 Pydantic 校验，DeepSeek 专用文本降级不会将非法情绪传给前端。

配置：python-dotenv 读取项目根目录 .env，DEEPSEEK_API_KEY 用 SecretStr 存储；模型、地址、思考开关、超时均可配置。示例文件无真实密钥，静态目录限定 frontend。

数据：沿用五张表，补列迁移；会话消息持久化，长期记忆单独管理，最近上下文和检索结果均有上限。测试不依赖或覆盖主数据库，真实模型 smoke 使用 tmp 中的隔离库。

验证包括：SDK 参数契约、认证失败与超时脱敏、真实非流式中文、多轮和跨会话记忆、实际进程重启、浏览器 SSE 与动画、历史管理、记忆编辑删除、历史加载失败恢复。

不开发真实硬件驱动或音频协议。
