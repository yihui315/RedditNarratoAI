# CLAUDE.md - RedditNarratoAI v4.0 项目约定

## 项目概述
Reddit帖子 / YouTube短剧 → AI文案改写 → 14-Agent全自动生产 → 多平台发布
v4.0: 融合binghe操盘手灵魂 = 真正0焦虑内容工厂

## 架构
- **Pipeline模式**: `app/pipeline.py` - Reddit帖子→视频（单Agent链）
- **Agent模式**: `app/agents/orchestrator.py` - 14-Agent编排器（v4.0）
  - PersonaMaster → TopicEngine → CompetitorDecode → MaterialScout
  - → PlotAnalyzer → ScriptWriter → ReviewDiagnosis → VoiceAgent
  - → BrollMatcher → VideoGen → VideoEditor → SEO → Publish
  - + DailyOperator (Supervisor操盘手模式)

## 关键约定
1. 所有Agent继承 `app/agents/base.py::BaseAgent`，必须实现 `run()` 和 `verify()`
2. LLM调用统一通过 `app/services/llm.py::generate_response_from_config()`
3. 配置通过 `config.toml` 加载，Agent通过构造函数接收 config dict
4. 输出目录: `./output/` (视频) 和 `./output/agents/` (Agent工作文件)
5. 持久化资产: `config/persona.json`, `config/formula-library.json`, `config/hooks-library.json`
6. 内容日历: `config/content-calendar/` (DailyOperator自动生成)

## 常见坑
- `app/config/__init__.py` 必须用 `from . import config` (相对导入)，否则循环导入
- MoviePy 2.x API: 使用 `moviepy==2.1.1`，不是旧的 `moviepy.editor`
- Edge TTS rate 格式: `"+0%"`, `"+50%"`, `"-20%"` (字符串)
- Pexels/Kling/Runway API Key 为空时，对应Agent自动跳过（优雅降级）
- PersonaMaster 首次运行无 persona.json 时使用默认画像（不报错）
- CompetitorDecode 自动追加公式库/钩子库（去重），不会覆盖已有条目

## 测试
```bash
python -m pytest tests/ -v              # 所有测试
python -m pytest tests/test_agents.py   # Agent测试
python -m pytest tests/test_v3.py       # v3.0功能测试
python -m pytest tests/test_v4.py       # v4.0新功能测试
```

## 部署
```bash
docker compose up -d --build  # Docker一键部署
# 或
pip install -r requirements.txt && streamlit run webui.py
```

## v3.0文件
- `app/agents/video_gen.py` - AI视频生成Agent (Kling/Runway)
- `app/agents/broll_matcher.py` - B-roll素材匹配Agent (Pexels)
- `app/agents/seo_agent.py` - SEO优化Agent
- `app/agents/publish_agent.py` - 自动发布Agent
- `app/prompts/` - v3.0爆款Prompt包
- `Dockerfile` + `docker-compose.yml` - Docker部署
- `MIGRATION_V3.md` - 迁移指南

## v4.0新增文件
- `app/agents/persona_master.py` - 永久画像持久化Agent
- `app/agents/competitor_decode.py` - 竞品拆解Agent（自动存公式库）
- `app/agents/topic_engine.py` - 多模式选题引擎Agent (mine/hot/rival/flash)
- `app/agents/review_diagnosis.py` - 5维度爆款评分Agent
- `app/agents/daily_operator.py` - 每日操盘手Supervisor Agent
- `config/formula-library.json` - 爆款公式库（自动积累）
- `config/hooks-library.json` - 钩子库 + 金句库
- `app/prompts/v4_*.txt` - v4.0 Prompt模板
