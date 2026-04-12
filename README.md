# RedditNarratoAI

Reddit帖子转AI影视解说视频 - 合并 NarratoAI + RedditVideoMakerBot

## 功能特性

- **Reddit数据获取** - 支持Subreddit、Post链接、Post ID
- **AI文案改写** - 使用deepseek-r1:32b (Ollama) 将Reddit帖子/评论改为解说文案
- **多TTS引擎** - Edge TTS (默认)、ElevenLabs、gTTS
- **智能字幕** - LLM语义分析断句，SRT格式
- **视频剪辑** - MoviePy实现影视级剪辑，支持剪映草稿导出
- **多来源输入** - Reddit链接、B站视频、本地视频
- **🆕 全自动短剧解说Agent** - 5个AI Agent协作：素材识别→剧情分析→文案改写→配音→剪辑，零人工干预

## 技术栈

| 组件 | 技术 |
|------|------|
| 数据获取 | PRAW (Reddit API) |
| AI改写 | deepseek-r1:32b (Ollama) |
| TTS | Edge TTS / ElevenLabs / gTTS |
| 字幕 | SRT格式 + MoviePy |
| 视频 | MoviePy + FFmpeg |
| YouTube素材 | yt-dlp（自动搜索+下载） |
| Agent框架 | 自研多Agent编排器 |

## 项目结构

```
RedditNarratoAI/
├── app/
│   ├── agents/               # 🆕 多Agent系统
│   │   ├── base.py           # Agent基类（Verification Loop）
│   │   ├── material_scout.py # Agent 1: YouTube素材识别
│   │   ├── plot_analyzer.py  # Agent 2: 剧情提取&冲突分析
│   │   ├── script_writer.py  # Agent 3: 爆款文案改写
│   │   ├── voice_agent.py    # Agent 4: 情绪配音
│   │   ├── video_editor.py   # Agent 5: 自动剪辑&输出
│   │   └── orchestrator.py   # 多Agent编排器
│   ├── services/
│   │   ├── reddit/           # Reddit数据获取
│   │   ├── llm.py            # LLM调用
│   │   ├── voice.py          # 语音合成
│   │   ├── video.py          # 视频剪辑
│   │   └── subtitle.py       # 字幕生成
│   ├── pipeline.py           # Reddit视频流水线
│   └── config/               # 配置管理
├── cli.py                    # 🆕 命令行入口
├── webui.py                  # Web界面入口
├── tests/                    # 单元测试
├── config.example.toml       # 配置示例
└── requirements.txt          # 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.toml config.toml
# 编辑 config.toml 填入 Reddit API 凭证和LLM设置
```

### 3. 运行

```bash
# Web界面
streamlit run webui.py

# Reddit流水线 (命令行)
python cli.py reddit --url "https://reddit.com/r/AskReddit/comments/xxx"

# 🆕 全自动短剧解说Agent（搜索YouTube关键词）
python cli.py agent --keywords "short drama revenge"

# 🆕 指定YouTube视频URL
python cli.py agent --url "https://youtube.com/watch?v=xxx"

# 🆕 批量模式（最多处理5条）
python cli.py agent --keywords "短剧 逆袭" --max-videos 5

# 🆕 导出结果为JSON
python cli.py agent --keywords "sweet drama" --output-json results.json
```

## 流水线流程

### Reddit流水线（原有）
```
Reddit URL ──[PRAW]──→ 帖子/评论内容
    ──[deepseek-r1]──→ AI改写解说文案
    ──[Edge TTS]──→ 配音音频
    ──[LLM断句]──→ SRT字幕
    ──[MoviePy]──→ 最终视频
```

### 🆕 全自动短剧Agent流水线
```
关键词/URL
  ↓ [Agent 1: MaterialScout] YouTube搜索→下载字幕/视频
  ↓ [Agent 2: PlotAnalyzer]  LLM剧情提取→冲突/反转/人物JSON
  ↓ [Agent 3: ScriptWriter]  爆款文案改写（30-60秒口语化解说）
  ↓ [Agent 4: VoiceAgent]    情绪TTS配音 + 时间戳
  ↓ [Agent 5: VideoEditor]   自动剪辑→字幕→BGM→MP4 + SEO元数据
  ↓
最终输出: MP4视频 + 标题/描述/标签
```

### Agent系统设计原则
- **Verification Loop**: 每个Agent执行后自动验证结果，失败自动重试
- **模块化**: 5个Agent独立运行，可单独替换或扩展
- **可复用**: 所有Agent继承统一基类，统一接口
- **渐进降级**: 任何Agent失败不影响其他素材的处理

## 配置说明

`config.toml` 新增配置项：

```toml
[youtube]
max_results = 5          # 每次搜索最多返回几条
min_views = 500000       # 最低播放量筛选
subtitle_language = "zh" # 优先下载的字幕语言

[agents]
work_dir = "./output/agents"  # Agent工作目录
max_retries = 3               # 单个Agent最大重试次数
```

## 测试

```bash
python -m pytest tests/ -v
```

## License

MIT
