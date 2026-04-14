"""
电影自动浓缩解说系统 - Movie Auto-Narration Pipeline
=======================================================
输入：电影视频文件
输出：3段各约5分钟的解说视频脚本 + 渲染指令

6步流水线（Prompt Chaining）：
  Stage 1: 章节摘要整理  → chapters.json
  Stage 2: 三段式大纲     → outline.json
  Stage 3: 详细脚本生成   → script_part{1,2,3}.json
  Stage 4: Reflection自检 → final_script_part{1,2,3}.json
  Stage 5: 镜头提示生成   → scene_prompts_part{1,2,3}.json
  Stage 6: 渲染清单       → render_manifest.json

核心执行模型: MiniMax 2.7 (via OpenAI-compatible API)
本地工具: WhisperX (转写), PySceneDetect (镜头切分), FFmpeg (渲染)
"""
from app.services.movie.pipeline import MovieNarrationPipeline

__all__ = ["MovieNarrationPipeline"]
