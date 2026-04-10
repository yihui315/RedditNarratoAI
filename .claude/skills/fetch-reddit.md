# Skill: /fetch-reddit

## 概述
从 Reddit 获取帖子和评论数据，输出结构化 JSON。

## 输入
- Reddit URL（如 `https://reddit.com/r/AskReddit/comments/abc123`）
- 或 Post ID（如 `abc123`）

## 输出
```json
{
  "thread_title": "帖子标题",
  "thread_post": "帖子正文",
  "thread_id": "abc123",
  "thread_url": "https://reddit.com/...",
  "upvotes": 1234,
  "upvote_ratio": 0.95,
  "is_nsfw": false,
  "num_comments": 50,
  "comments": [
    {
      "comment_body": "评论内容",
      "comment_id": "xyz789",
      "author": "user123",
      "score": 100
    }
  ]
}
```

## 逻辑
1. 解析 URL → 提取 `post_id`（支持多种 URL 格式）
2. PRAW 连接 → 使用 `config.toml` 中的 `[reddit].creds`
3. 获取帖子标题、正文、元数据
4. 获取评论，按 upvote 排序，取 top-N（默认 10，可配置）
5. 过滤 `[removed]` / `[deleted]` 评论

## Verification
- 标题非空
- 评论数 ≥ 1（警告但不阻塞）
- 无 NSFW 内容标记（可配置跳过）
- 无异常字符或编码问题

## 实现文件
- `app/services/reddit/reddit_fetcher.py` → `RedditFetcher` 类
- `app/services/reddit/__init__.py` → 导出 `RedditFetcher`, `RedditContent`

## 配置
```toml
[reddit]
creds = { client_id = "...", client_secret = "...", username = "...", password = "..." }
top_comments = 10  # 获取 top N 条评论
```
