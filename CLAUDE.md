# CLAUDE.md - RedditNarratoAI v5.0 项目约定

## 项目概述
双模式短剧超级操盘手 → 18-Agent全自动生产 → 多平台发布
- **解说模式**: Reddit帖子 / YouTube短剧 → AI文案改写 → 成品视频
- **原创短剧模式**: 一句话主题 → 角色 → 分镜 → 配音 → AI视频 → 成品
v5.0: 融合9个竞品核心长处 = 2026最强短剧内容超级操盘手

## 架构
- **Pipeline模式**: `app/pipeline.py` - Reddit帖子→视频（单Agent链）
- **Agent模式**: `app/agents/orchestrator.py` - 18-Agent编排器（v5.0）
  - narration（解说）: PersonaMaster → TopicEngine → CompetitorDecode → MaterialScout
    → PlotAnalyzer → ScriptWriter → ReviewDiagnosis → VoiceAgent
    → BrollMatcher → VideoGen → VideoEditor → VisualAsset → SEO → Publish
  - drama（原创短剧）: PersonaMaster → ScriptWriter → CharacterGen → StoryboardBreaker
    → DubbingAgent → VideoGen → VideoEditor → VisualAsset → SEO → Publish
  - + DailyOperator (Supervisor操盘手模式)

## 关键约定
1. 所有Agent继承 `app/agents/base.py::BaseAgent`，必须实现 `run()` 和 `verify()`
2. LLM调用统一通过 `app/services/llm.py::generate_response_from_config()`
3. 配置通过 `config.toml` 加载，Agent通过构造函数接收 config dict
4. 输出目录: `./output/` (视频) 和 `./output/agents/` (Agent工作文件)
5. 持久化资产: `config/persona.json`, `config/formula-library.json`, `config/hooks-library.json`, `config/memory.json`
6. 内容日历: `config/content-calendar/` (DailyOperator自动生成)
7. 跨会话记忆: `config/memory.json` (Orchestrator自动管理，最近100条)

## 常见坑
- `app/config/__init__.py` 必须用 `from . import config` (相对导入)，否则循环导入
- MoviePy 2.x API: 使用 `moviepy==2.1.1`，不是旧的 `moviepy.editor`
- Edge TTS rate 格式: `"+0%"`, `"+50%"`, `"-20%"` (字符串)
- Pexels/Kling/Runway API Key 为空时，对应Agent自动跳过（优雅降级）
- GPT-SoVITS API 为空时，DubbingAgent自动降级到Edge TTS（不报错）
- MiniMax/Vidu API Key 为空时，VisualAssetAgent使用Pillow本地生成（不报错）
- PersonaMaster 首次运行无 persona.json 时使用默认画像（不报错）
- CompetitorDecode 自动追加公式库/钩子库（去重），不会覆盖已有条目
- CharacterGenAgent LLM失败时返回默认角色模板（protagonist + antagonist）
- StoryboardBreakerAgent LLM失败时按段落自动切分为分镜

## 测试
```bash
python -m pytest tests/ -v              # 所有测试
python -m pytest tests/test_agents.py   # Agent测试
python -m pytest tests/test_v3.py       # v3.0功能测试
python -m pytest tests/test_v4.py       # v4.0新功能测试
python -m pytest tests/test_v5.py       # v5.0新功能测试
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

## v5.0新增文件
- `app/agents/character_gen.py` - 角色生成Agent (huobao-drama风格)
- `app/agents/storyboard_breaker.py` - 分镜拆解Agent (Toonflow+huobao)
- `app/agents/dubbing_agent.py` - 高质克隆配音Agent (VideoLingo GPT-SoVITS)
- `app/agents/visual_asset.py` - 视觉卡片/封面Agent (baoyu-skills)
- `config/memory.json` - 跨会话记忆持久化 (Toonflow记忆层)
- `app/prompts/v5_daily_operator.txt` - v5.0 Prompt模板
