# RedditNarratoAI

Reddit帖子转AI影视解说视频 - 合并 NarratoAI + RedditVideoMakerBot

## 功能特性

- **Reddit数据获取** - 支持Subreddit、Post链接、Post ID
- **AI文案改写** - 使用deepseek-r1:32b (Ollama) 将Reddit帖子/评论改为解说文案
- **多TTS引擎** - Edge TTS (默认)、ElevenLabs、gTTS
- **智能字幕** - LLM语义分析断句，SRT格式
- **视频剪辑** - MoviePy实现影视级剪辑，支持剪映草稿导出
- **多来源输入** - Reddit链接、B站视频、本地视频

## 技术栈

| 组件 | 技术 |
|------|------|
| 数据获取 | PRAW (Reddit API) |
| AI改写 | deepseek-r1:32b (Ollama) |
| TTS | Edge TTS / ElevenLabs / gTTS |
| 字幕 | SRT格式 + MoviePy |
| 视频 | MoviePy + FFmpeg |

## 项目结构

```
RedditNarratoAI/
├── app/
│   ├── services/
│   │   ├── reddit/          # Reddit数据获取 (来自RedditVideoMakerBot)
│   │   ├── llm.py           # LLM调用 (来自NarratoAI)
│   │   ├── tts.py           # 语音合成 (来自NarratoAI)
│   │   ├── video/           # 视频剪辑 (来自NarratoAI)
│   │   └── subtitle.py      # 字幕生成 (来自NarratoAI)
│   ├── pipeline.py          # 核心流水线
│   └── config/              # 配置管理
├── webui.py                 # Web界面入口
├── config.example.toml      # 配置示例
└── requirements.txt         # 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.toml config.toml
# 编辑 config.toml 填入 Reddit API 凭证
```

### 3. 运行

```bash
# Web界面
streamlit run webui.py

# 命令行
python -m app.pipeline --reddit-url "https://reddit.com/r/AskReddit/comments/xxx"
```

## 流水线流程

```
Reddit URL ──[PRAW]──→ 帖子/评论内容
    ──[deepseek-r1]──→ AI改写解说文案
    ──[Edge TTS]──→ 配音音频
    ──[LLM断句]──→ SRT字幕
    ──[MoviePy]──→ 最终视频
```

## License

MIT
