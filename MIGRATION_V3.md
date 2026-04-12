# RedditNarratoAI v3.0 迁移指南

## 从 v0.2.0 / v1.0 / v2.0 升级到 v3.0

### 3分钟迁移步骤

#### Step 1: 更新代码
```bash
git pull origin main
# 或手动覆盖所有文件
```

#### Step 2: 更新配置
```bash
cp config.toml config.toml.bak  # 备份旧配置
# 将 config.example.toml 中的新段落追加到你的 config.toml
```

需要追加的新配置段:
```toml
[video_gen]
mode = "moviepy"              # moviepy (本地免费) / kling / runway
kling_api_key = ""            # 可选
runway_api_key = ""           # 可选

[pexels]
api_key = ""                  # 可选，用于B-roll自动匹配

[publish]
auto_publish = false
platforms = ["tiktok", "youtube_shorts"]
tiktok_access_token = ""
youtube_api_key = ""
```

#### Step 3: 安装依赖 & 启动
```bash
# 方式A: Docker（推荐，5分钟）
docker compose up -d --build
# 访问 http://localhost:8501

# 方式B: 本地运行
pip install -r requirements.txt
streamlit run webui.py
```

### v3.0 新增功能
| 功能 | 说明 | 需要配置 |
|------|------|----------|
| 9-Agent Pipeline | 从5个Agent扩展到9个 | 无，自动 |
| B-roll自动匹配 | Pexels免费素材匹配 | `[pexels] api_key` |
| AI视频生成 | Kling/Runway文本转视频 | `[video_gen]` API Key |
| SEO优化 | 自动生成标题/标签/话题 | 无，使用LLM |
| 自动发布 | TikTok/YouTube/Instagram | `[publish]` tokens |
| Docker部署 | 一键拉起全环境 | 无 |
| 爆款Prompt v3.0 | 300万点赞特征优化 | 无 |
| 自我迭代 | 24h数据反馈优化Prompt | 无 |

### 兼容性说明
- ✅ **完全向后兼容**: 所有v0.2.0的配置和功能保持不变
- ✅ **新Agent可选**: video_gen/broll/publish 无API Key时自动跳过
- ✅ **CLI不变**: `python cli.py agent --url ...` 和 `python cli.py reddit --url ...` 用法不变
- ✅ **测试不变**: 所有原有测试保持通过

### 验证升级成功
```bash
# 1. 运行测试
python -m pytest tests/ -v

# 2. CLI测试
python cli.py config check

# 3. WebUI测试
# 打开 http://localhost:8501 → 确认显示 "v3.0"
```

### 故障排除
- **ImportError**: 运行 `pip install -r requirements.txt` 更新依赖
- **Docker GPU**: 如无NVIDIA GPU，删除docker-compose.yml中的`deploy.resources`段
- **Kling/Runway超时**: 默认5分钟超时，可在代码中调整`timeout`参数
