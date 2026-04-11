# CLAUDE.md - RedditNarratoAI v3.0 项目约定

## 项目概述
Reddit帖子 / YouTube短剧 → AI文案改写 → 9-Agent全自动生产 → 多平台发布

## 架构
- **Pipeline模式**: `app/pipeline.py` - Reddit帖子→视频（单Agent链）
- **Agent模式**: `app/agents/orchestrator.py` - 9-Agent编排器（v3.0）
  - MaterialScout → PlotAnalyzer → ScriptWriter → VoiceAgent
  - → BrollMatcher → VideoGen → VideoEditor → SEO → Publish

## 关键约定
1. 所有Agent继承 `app/agents/base.py::BaseAgent`，必须实现 `run()` 和 `verify()`
2. LLM调用统一通过 `app/services/llm.py::generate_response_from_config()`
3. 配置通过 `config.toml` 加载，Agent通过构造函数接收 config dict
4. 输出目录: `./output/` (视频) 和 `./output/agents/` (Agent工作文件)

## 常见坑
- `app/config/__init__.py` 必须用 `from . import config` (相对导入)，否则循环导入
- MoviePy 2.x API: 使用 `moviepy==2.1.1`，不是旧的 `moviepy.editor`
- Edge TTS rate 格式: `"+0%"`, `"+50%"`, `"-20%"` (字符串)
- Pexels/Kling/Runway API Key 为空时，对应Agent自动跳过（优雅降级）

## 测试
```bash
python -m pytest tests/ -v              # 所有测试
python -m pytest tests/test_agents.py   # Agent测试
python -m pytest tests/test_v3.py       # v3.0新功能测试
```

## 部署
```bash
docker compose up -d --build  # Docker一键部署
# 或
pip install -r requirements.txt && streamlit run webui.py
```

## v3.0新增文件
- `app/agents/video_gen.py` - AI视频生成Agent (Kling/Runway)
- `app/agents/broll_matcher.py` - B-roll素材匹配Agent (Pexels)
- `app/agents/seo_agent.py` - SEO优化Agent
- `app/agents/publish_agent.py` - 自动发布Agent
- `app/prompts/` - v3.0爆款Prompt包
- `Dockerfile` + `docker-compose.yml` - Docker部署
- `MIGRATION_V3.md` - 迁移指南
