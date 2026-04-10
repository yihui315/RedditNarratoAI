# RedditNarratoAI

Reddit帖子转AI影视解说视频 —— Agentic Engineering 架构

## 功能特性

### 核心流水线
- **Reddit数据获取** — PRAW 支持 Subreddit / Post链接 / Post ID
- **AI文案改写** — Subagent 并行（评论总结 + 情绪曲线 + B-roll 关键词）→ LLM 生成中文影视解说文案
- **中文TTS配音** — Edge TTS，段落间情绪化停顿
- **动态字幕** — 根据情绪标签切换颜色/风格（ASS + SRT 双格式）
- **视频合成** — B-roll + 配音 + 动态字幕 + BGM + 转场 → 1080p MP4

### 影视解说专属
- **自动 B-roll** — Pexels API 在线搜索 + 本地 stock 降级
- **动态字幕样式** — tense(红) / emotional(白) / upbeat(黄) / calm(灰)
- **背景音乐情绪匹配** — 按情绪标签自动选择 BGM，自动音量控制
- **转场效果** — crossfade / fade-to-black / slide-left

### 工程能力
- **Verification Loop** — 每步自动验证（内容完整性、文案质量、音频时长、视频完整性）
- **批量处理** — 多 URL 并行处理（`ProcessPoolExecutor`）
- **CLI + WebUI** — 命令行工具 + Streamlit 网页界面
- **Docker** — 一键容器化部署（含 Ollama LLM 服务）
- **Skills** — 5 个独立 Skill 定义（`.claude/skills/`）

## 技术栈

| 组件 | 技术 |
|------|------|
| Reddit数据 | PRAW |
| AI文案 | deepseek-r1:32b (Ollama) / OpenAI 兼容 |
| TTS | Edge TTS (中文) |
| 字幕 | SRT + ASS (动态样式) |
| 视频 | MoviePy + FFmpeg |
| B-roll | Pexels API |
| CLI | Click + Rich |
| 容器 | Docker + Docker Compose |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.toml config.toml
# 编辑 config.toml 填入:
#   - Reddit API 凭证
#   - LLM 配置（Ollama 地址/模型）
#   - Pexels API Key（可选，用于 B-roll）
```

### 3. 运行

```bash
# 单个 URL
python cli.py single "https://reddit.com/r/AskReddit/comments/xxx"

# 只生成文案（不合成视频）
python cli.py single "https://reddit.com/r/AskReddit/comments/xxx" --dry-run

# 批量处理
python cli.py batch urls.txt --workers 2

# Web 界面
streamlit run webui.py
```

### 4. Docker 运行

```bash
# 构建并启动所有服务（App + Ollama + WebUI）
docker-compose up -d

# 拉取 LLM 模型（首次）
docker exec -it ollama ollama pull deepseek-r1:32b

# 处理单个 URL
docker-compose run --rm app single "https://reddit.com/r/AskReddit/comments/xxx"
```

### 5. Make 快捷命令

```bash
make setup              # 安装依赖
make run URL=<url>      # 处理单个 URL
make batch URLS=<file>  # 批量处理
make dry-run URL=<url>  # 只生成文案
make webui              # 启动 Web 界面
make docker-build       # 构建 Docker 镜像
make test               # 运行测试
make clean              # 清理输出
```

## CLI 用法

```
Usage: cli.py [OPTIONS] COMMAND [ARGS]...

  🎬 RedditNarratoAI - Reddit帖子转AI影视解说视频

Commands:
  single  处理单个 Reddit URL 生成视频
  batch   批量处理多个 Reddit URL

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Single Options:
  --output-dir, -o PATH   输出目录
  --no-broll              禁用 B-roll
  --no-bgm                禁用背景音乐
  --voice TEXT            TTS 声音名称
  --model TEXT            LLM 模型名称
  --dry-run               只生成文案不合成视频

Batch Options:
  --workers, -w INT       并行 worker 数（默认 2）
  (plus all single options)
```

## 项目结构

```
RedditNarratoAI/
├── CLAUDE.md                          # Agentic 规则 + 已知坑
├── Dockerfile                         # Docker 镜像
├── docker-compose.yml                 # Docker Compose (App + Ollama)
├── Makefile                           # Make 快捷命令
├── cli.py                             # CLI 主程序
├── webui.py                           # Web 界面 (Streamlit)
├── config.toml                        # 配置文件
├── requirements.txt                   # Python 依赖
│
├── .claude/skills/                    # Agentic Skills 定义
│   ├── fetch-reddit.md
│   ├── generate-cinematic-script.md
│   ├── chinese-tts-pro.md
│   ├── synthesize-cinematic-video.md
│   └── batch-process.md
│
├── app/
│   ├── pipeline.py                    # 核心流水线 (Subagent 并行 + Verification)
│   ├── batch.py                       # 批量处理引擎
│   ├── verification.py                # Verification Loop
│   ├── config/                        # 配置管理
│   ├── models/                        # 数据模型
│   ├── services/
│   │   ├── reddit/                    # Reddit 数据获取
│   │   ├── llm.py                     # LLM 调用
│   │   ├── voice.py                   # TTS 引擎
│   │   ├── subtitle.py                # 字幕生成
│   │   ├── video.py                   # 视频合成
│   │   ├── broll.py                   # B-roll 自动匹配
│   │   ├── bgm.py                     # BGM 情绪匹配
│   │   ├── transitions.py             # 转场效果
│   │   └── dynamic_subtitle.py        # 动态字幕样式
│   └── utils/
│
├── resource/bgm/                      # BGM 资源（按情绪分类）
│   ├── tense/
│   ├── emotional/
│   ├── upbeat/
│   └── calm/
│
├── tests/                             # 测试
└── output/                            # 视频输出
```

## 流水线流程

```
Reddit URL
  │
  ├── [1] PRAW 获取帖子 + 评论
  │     └── Verification: 标题非空、评论数检查
  │
  ├── [2] Subagent 并行分析 ──────────────────────┐
  │     ├── Subagent 1: 评论总结 (LLM)            │
  │     ├── Subagent 2: 情绪曲线 (LLM)            │ asyncio.gather()
  │     └── Subagent 3: B-roll关键词 (LLM)        │
  │                                                │
  │     合并 → LLM 生成带标注的影视解说文案 ←──────┘
  │     └── Verification: 字数、段落数、标签完整性
  │
  ├── [3] Edge TTS 逐段配音 + 情绪化停顿
  │     └── Verification: 文件存在、时长范围
  │
  ├── [4] 动态字幕生成 (ASS + SRT)
  │
  └── [5] 视频合成
        ├── B-roll 视频匹配 (Pexels API / 本地)
        ├── BGM 情绪匹配 (resource/bgm/)
        ├── 转场效果 (crossfade / fade)
        └── MoviePy 合成 → 1080p MP4
              └── Verification: 文件大小、时长匹配
```

## 配置说明

关键配置项（`config.toml`）:

| 配置段 | 说明 |
|--------|------|
| `[reddit]` | Reddit API 凭证 |
| `[llm]` | LLM 提供商/模型/API地址 |
| `[tts]` | TTS 引擎/语音/语速 |
| `[video]` | 视频输出参数（分辨率/帧率） |
| `[subtitle]` | 字幕字体/颜色/位置 |
| `[broll]` | B-roll 启用/Pexels API Key/缓存 |
| `[bgm]` | BGM 启用/音量/crossfade |
| `[transition]` | 转场类型/时长 |
| `[batch]` | 批量处理 worker 数 |

## License

MIT
