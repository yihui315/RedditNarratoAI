# Skill: /synthesize-cinematic-video

## 概述
将音频、时间轴、B-roll 和字幕合成为最终影视解说视频。

## 输入
- 音频文件路径（MP3）
- 时间轴 JSON（`[{text, start_ms, end_ms, mood, broll_keywords}]`）
- 文案全文

## 输出
- 最终 MP4 视频（1080p, H.264）

## 逻辑

### 1. B-roll 获取 (`app/services/broll.py`)
- 根据每段 `broll_keywords` 从 Pexels API 搜索下载视频片段
- 降级: 无 API Key 时，从 `resource/videos/` 本地匹配
- 降级: 无匹配时，使用纯色背景
- 缓存: 相同关键词不重复下载
- 裁剪: 自动裁剪到段落时长

### 2. 动态字幕 (`app/services/dynamic_subtitle.py`)
- 根据情绪标签切换字幕样式:
  - `tense` → 红色高亮 (#FF4444)、加粗
  - `emotional` → 白色 (#FFFFFF)、柔和阴影
  - `upbeat` → 黄色 (#FFD700)、活力风格
  - `calm` → 淡灰 (#CCCCCC)、透明底

### 3. 背景音乐 (`app/services/bgm.py`)
- 根据情绪标签选择 `resource/bgm/{mood}/` 下的音频
- 自动调整音量（默认 0.15，不盖过语音）
- 段落切换时 crossfade

### 4. 转场效果 (`app/services/transitions.py`)
- 段落切换时插入转场（默认 0.5s crossfade）
- 支持: `crossfade` / `fade_to_black` / `slide_left`

### 5. MoviePy 合成
- 层级: B-roll 视频底层 → 字幕覆盖层 → 配音音轨 → BGM 音轨
- 输出: 1080p MP4, H.264+AAC

## Verification
- 视频文件存在且大小 > 100KB
- 视频时长与音频时长匹配（误差 < 1s）
- ffprobe 检查无报错

## 配置
```toml
[broll]
enabled = true
provider = "pexels"
pexels_api_key = ""
fallback = "local"
cache_dir = "./cache/broll"

[bgm]
enabled = true
volume = 0.15
crossfade_duration = 1.0

[transition]
enabled = true
type = "crossfade"
duration = 0.5
```
