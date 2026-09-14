"""EngEduScope｜轻量 LLM 接入层（M3）。

    provider.py   本地 AI Settings 配置 + 单一调用链 complete_json()（OpenAI 兼容 / Anthropic / mock），统一错误类型
    prompts.py    系统提示与用户提示模板（家长分析 / 教育工作者分析 / 方案调整），独立于页面
    schemas.py    结构化输出的最小校验与规范化（映射回正式 Taxonomy、枚举值、条数）
    mock.py       无 API Key 时用于结构测试 / 演示的确定性 fixture（UI 会明确标注 Mock）

原则：API Key 通过 AI Settings 保存到私有本地配置（兼容环境变量）；业务逻辑不依赖具体 Provider；不引入 LangChain / Agent 框架。
"""
