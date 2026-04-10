# CLAUDE.md - RedditNarratoAI Agentic Rules

## 项目概述
RedditNarratoAI: Reddit帖子 → AI影视解说文案 → 中文TTS配音 → 带字幕B-roll视频

## 项目规则
- 所有服务函数接受 `config: dict` 参数，从 `config.toml` 加载
- 使用 `loguru` 记录日志，不使用 `print()`
- 使用 relative import（`from . import config`）避免 circular import
- Edge TTS voice 默认 `zh-CN-XiaoxiaoNeural`
- 新功能必须 graceful degradation：缺少 API Key / 资源时降级而不崩溃
- 每个 Skill 独立可测，可单独调用不跑全流程

## 已知坑
- `app/config/__init__.py` 必须用 `from . import config` 不能用 `from app.config import config`（circular import）
- `edge-tts` SubMaker API 新旧版本不兼容，`voice.py` 中有兼容层（`new_sub_maker()`）
- `google-generativeai` 是可选依赖，用 `try/except` 包裹
- `moviepy` 的 `TextClip` 需要 ImageMagick，某些环境下不可用
- `config.py` 中 `root_dir` 是从 `config.py` 文件位置向上3层（项目根目录）

## 构建和测试
```bash
pip install -r requirements.txt
python -m pytest tests/
python cli.py single <url> --dry-run
```

## Skills 索引
- `/fetch-reddit` → Reddit 数据获取（PRAW）
- `/generate-cinematic-script` → 影视解说文案（LLM + Subagent 并行）
- `/chinese-tts-pro` → 中文 TTS 专业版（Edge TTS + 情绪停顿）
- `/synthesize-cinematic-video` → 影视视频合成（B-roll + 动态字幕 + BGM + 转场）
- `/batch-process` → 批量 URL 并行处理

## 架构约定
- Pipeline 入口: `app/pipeline.py` → `RedditVideoPipeline.run()`
- CLI 入口: `cli.py` （Click 框架）
- Web UI 入口: `webui.py` （Streamlit）
- 配置: `config.toml` → `app/config/config.py` 加载
- 验证: `app/verification.py` → 每步自动自测
- 批量: `app/batch.py` → `concurrent.futures` 并行
