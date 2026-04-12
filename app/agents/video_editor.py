"""
Agent 5: 自动剪辑 & 输出Agent（Video Editor）
用MoviePy将原视频素材 + 配音 + 字幕合成为最终短视频
自动加字幕、背景音乐、控制画面节奏
"""

import os
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.subtitle import create_srt_from_text
from app.services.video import create_video_from_segments
from app.pipeline import VideoSegment


class VideoEditorAgent(BaseAgent):
    """
    自动剪辑Agent

    输入: 原始视频路径 + 配音路径 + 解说文案 + 时长信息
    输出: 最终MP4成品 + 标题/描述/标签
    """

    def __init__(self, config: dict):
        super().__init__(config, name="VideoEditor")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说文案
            audio_path (str): 配音音频路径
            durations (list[float]): 每段时长
            source_video_path (str): 原始素材视频路径
            session_id (str): 会话ID
            title (str): 视频标题
            analysis (dict): 剧情分析（用于生成标签）
        """
        script = input_data.get("script", "")
        audio_path = input_data.get("audio_path", "")
        durations = input_data.get("durations", [])
        source_video = input_data.get("source_video_path", "")
        session_id = input_data.get("session_id", "default")
        title = input_data.get("title", "短剧解说")
        analysis = input_data.get("analysis", {})

        if not script or not audio_path:
            return AgentResult(
                success=False,
                error="缺少文案或音频",
            )

        session_dir = str(self.output_dir / session_id)
        os.makedirs(session_dir, exist_ok=True)

        try:
            # Step 1: 生成字幕文件（使用TTS实际时长精确同步）
            subtitle_path = os.path.join(session_dir, "subtitle.srt")
            create_srt_from_text(
                text=script,
                output_path=subtitle_path,
                config=self.config,
                durations=durations,
            )

            # Step 2: 构造VideoSegment列表
            segments = self._build_segments(script, audio_path, durations)

            # Step 3: 合成视频
            video_path = create_video_from_segments(
                segments=segments,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                output_dir=session_dir,
                config=self.config,
                title=title,
            )

            if not video_path or not os.path.exists(video_path):
                return AgentResult(
                    success=False, error="视频合成失败"
                )

            # Step 4: 生成SEO元数据
            metadata = self._generate_metadata(title, analysis)
            metadata_path = os.path.join(session_dir, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            return AgentResult(
                success=True,
                data={
                    "video_path": video_path,
                    "subtitle_path": subtitle_path,
                    "metadata_path": metadata_path,
                    "metadata": metadata,
                    "session_id": session_id,
                },
            )

        except Exception as e:
            logger.error(f"[VideoEditor] 剪辑失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 最终视频文件存在且大小 > 100KB"""
        if not result.success:
            return False
        video_path = result.data.get("video_path", "")
        if not video_path or not os.path.exists(video_path):
            return False
        size = os.path.getsize(video_path)
        if size < 100 * 1024:
            logger.warning(
                f"[VideoEditor] 视频文件太小: {size} bytes"
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_segments(
        script: str, audio_path: str, durations: List[float]
    ) -> List[VideoSegment]:
        """将文案按段落切分为VideoSegment"""
        paragraphs = [p.strip() for p in script.split("\n") if p.strip()]
        segments = []
        current_time = 0.0

        for i, para in enumerate(paragraphs):
            dur = durations[i] if i < len(durations) else 3.0
            segments.append(
                VideoSegment(
                    text=para,
                    audio_path=audio_path,
                    start_time=current_time,
                    end_time=current_time + dur,
                )
            )
            current_time += dur

        return segments

    @staticmethod
    def _generate_metadata(title: str, analysis: dict) -> dict:
        """生成标题/描述/标签（SEO优化）"""
        genre = analysis.get("genre", "短剧")
        summary = analysis.get("summary", "")
        conflicts = analysis.get("conflicts", [])

        # 构造吸引点击的标题
        seo_title = title
        if conflicts:
            top_conflict = conflicts[0].get("description", "")
            if top_conflict and len(top_conflict) < 30:
                seo_title = f"{title}｜{top_conflict}"

        # 标签
        tags = [
            "短剧解说", genre, "热门短剧", "剧情解说",
            "AI解说", "短视频",
        ]
        characters = analysis.get("characters", [])
        for ch in characters[:3]:
            if ch.get("name"):
                tags.append(ch["name"])

        return {
            "title": seo_title,
            "description": f"{summary}\n\n#短剧解说 #{genre}",
            "tags": tags,
        }
