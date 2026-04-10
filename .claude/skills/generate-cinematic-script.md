# Skill: /generate-cinematic-script

## 概述
将 Reddit 内容改写为中文影视解说文案，带段落标记、情绪标注和 B-roll 关键词。

## 输入
- `RedditContent` JSON（来自 `/fetch-reddit`）

## 输出
带标注的影视解说文案：
```
[mood:tense][broll:dark alley night]
你绝对不会相信，这个看似普通的男人，竟然隐藏着一个惊天秘密。
---
[mood:emotional][broll:family dinner]
当他终于鼓起勇气说出真相的那一刻，所有人都沉默了。
---
[mood:upbeat][broll:sunrise city]
但故事的结局，却出乎所有人的意料。
```

## Subagent 并行架构
三个 Subagent 通过 `asyncio.gather()` 并行执行：

### Subagent 1: 评论总结
- 输入: top 评论列表
- 输出: 精炼摘要（提取关键观点和精彩回复）
- Prompt: "总结以下评论的核心观点，提炼最有故事性的内容"

### Subagent 2: 情绪曲线
- 输入: 帖子标题 + 正文
- 输出: `[{paragraph_hint, mood: "tense"|"emotional"|"upbeat"|"calm"}]`
- Prompt: "分析内容情绪走向，为每个段落标注情绪标签"

### Subagent 3: B-roll 关键词
- 输入: 帖子内容摘要
- 输出: `[{paragraph_hint, broll_keywords: ["keyword1", "keyword2"]}]`
- Prompt: "为每个段落建议1-2个适合搜索B-roll视频的英文关键词"

### 合并逻辑
主 Agent 将三者合并，调用 LLM 生成最终文案，每段带 `[mood:xxx]` 和 `[broll:xxx]` 标注。

## Verification
- 文案长度: 500-2000 字
- 段落数: ≥ 3
- 每段都有 `[mood:xxx]` 标签
- 每段都有 `[broll:xxx]` 标签
- 不含 "Reddit"、"帖子"、"评论" 等词

## 实现文件
- `app/pipeline.py` → `RedditVideoPipeline._generate_cinematic_script()`
- `app/services/llm.py` → `generate_script()` 基础 LLM 调用

## 配置
```toml
[llm]
provider = "openai"
api_base = "http://localhost:11434/v1"
model = "deepseek-r1:32b"
max_tokens = 4096
temperature = 0.7
```
