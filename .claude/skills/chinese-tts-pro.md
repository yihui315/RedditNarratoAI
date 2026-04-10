# Skill: /chinese-tts-pro

## 概述
将影视解说文案转为中文语音，支持情绪化停顿和精确时间轴输出。

## 输入
- 影视解说文案（带 `[mood:xxx]` 标注的文本）

## 输出
- 合并后的音频文件（MP3）
- 时间轴 JSON:
```json
[
  {"text": "段落文本", "start_ms": 0, "end_ms": 5200, "mood": "tense"},
  {"text": "段落文本", "start_ms": 5500, "end_ms": 11000, "mood": "emotional"}
]
```

## 逻辑
1. 解析文案，按 `---` 分段
2. 提取每段的 `[mood:xxx]` 和 `[broll:xxx]` 标注
3. Edge TTS 逐段生成音频
4. 根据情绪标签动态调整段落间停顿:
   - `tense` → 0.3s 短停顿（紧张节奏）
   - `emotional` → 0.8s 长停顿（留白感动）
   - `upbeat` → 0.3s 短停顿（节奏明快）
   - `calm` → 0.5s 中停顿（平缓过渡）
5. 合并所有音频段 + 静音间隔 → 完整音频
6. 计算精确时间轴

## Verification
- 总时长: 120s - 300s（2-5分钟）
- 每段音频文件存在且大小 > 0
- 时间轴条目数 = 段落数
- 时间轴无重叠、无间隙（允许停顿间隔）

## 实现文件
- `app/services/voice.py` → `generate_voice()` 基础 TTS
- `app/pipeline.py` → `RedditVideoPipeline._generate_voice_pro()` 增强版

## 配置
```toml
[tts]
provider = "edge"
voice = "zh-CN-XiaoxiaoNeural"
rate = "+0%"
pitch = "+0Hz"
volume = "+0%"
```
