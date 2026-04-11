"""
Agent 7: B-roll素材匹配Agent（B-roll Matcher）
根据脚本关键词自动从Pexels/Pixabay下载匹配的B-roll视频片段
"""

import os
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class BrollMatcherAgent(BaseAgent):
    """
    B-roll素材匹配Agent

    输入: 解说文案 + 剧情分析
    输出: 匹配的B-roll视频片段路径列表
    """

    def __init__(self, config: dict):
        super().__init__(config, name="BrollMatcher")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "broll"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        pexels_cfg = config.get("pexels", {})
        self.pexels_api_key = pexels_cfg.get("api_key", "") or os.getenv("PEXELS_API_KEY", "")
        self.max_clips = pexels_cfg.get("max_clips", 5)
        self.clip_duration = pexels_cfg.get("clip_duration", 10)  # seconds

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说文案
            analysis (dict): 剧情分析（用于提取关键词）
            session_id (str): 会话ID
        """
        script = input_data.get("script", "")
        analysis = input_data.get("analysis", {})
        session_id = input_data.get("session_id", "default")

        if not self.pexels_api_key:
            logger.info("[BrollMatcher] 未配置Pexels API Key，跳过B-roll下载")
            return AgentResult(
                success=True,
                data={
                    "broll_clips": [],
                    "message": "无Pexels API Key，跳过B-roll",
                },
            )

        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Extract keywords from analysis and script
        keywords = self._extract_keywords(script, analysis)
        if not keywords:
            return AgentResult(
                success=True,
                data={"broll_clips": [], "message": "无法提取关键词"},
            )

        try:
            clips = self._search_and_download(keywords, session_dir)
            return AgentResult(
                success=True,
                data={
                    "broll_clips": clips,
                    "keywords": keywords,
                    "clip_count": len(clips),
                },
            )
        except Exception as e:
            logger.error(f"[BrollMatcher] B-roll下载失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 即使没有B-roll也算通过（B-roll是可选增强）"""
        return result.success

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def _extract_keywords(self, script: str, analysis: dict) -> List[str]:
        """从剧情分析和脚本中提取B-roll搜索关键词"""
        keywords = []

        # From analysis
        genre = analysis.get("genre", "")
        if genre:
            keywords.append(genre)

        # From emotional peaks
        for peak in analysis.get("emotional_peaks", []):
            emotion = peak.get("emotion", "")
            if emotion:
                keywords.append(emotion)

        # From script - extract nouns/concepts (simple heuristic)
        # Look for common visual keywords
        visual_keywords = [
            "城市", "夜晚", "阳光", "大海", "山", "雨", "火", "战斗",
            "奔跑", "拥抱", "哭泣", "笑", "愤怒", "悲伤", "快乐",
            "city", "night", "sun", "ocean", "mountain", "rain", "fire",
            "fight", "run", "hug", "cry", "laugh", "anger", "sad", "happy",
            "revenge", "love", "mystery", "dramatic", "romantic",
        ]
        for kw in visual_keywords:
            if kw in script.lower():
                keywords.append(kw)

        # Deduplicate and limit
        seen = set()
        unique = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)
        return unique[: self.max_clips]

    # ------------------------------------------------------------------
    # Pexels API
    # ------------------------------------------------------------------

    def _search_and_download(
        self, keywords: List[str], output_dir: Path
    ) -> List[str]:
        """搜索Pexels并下载B-roll视频片段"""
        import requests

        clips = []
        headers = {"Authorization": self.pexels_api_key}

        for i, keyword in enumerate(keywords):
            try:
                resp = requests.get(
                    "https://api.pexels.com/videos/search",
                    params={
                        "query": keyword,
                        "per_page": 1,
                        "orientation": "landscape",
                        "size": "medium",
                    },
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.warning(f"[BrollMatcher] Pexels搜索失败 '{keyword}': {resp.status_code}")
                    continue

                videos = resp.json().get("videos", [])
                if not videos:
                    continue

                # Get the best quality video file under 720p
                video_files = videos[0].get("video_files", [])
                download_url = self._pick_best_file(video_files)
                if not download_url:
                    continue

                # Download
                clip_path = str(output_dir / f"broll_{i}.mp4")
                video_resp = requests.get(download_url, timeout=60)
                with open(clip_path, "wb") as f:
                    f.write(video_resp.content)

                if os.path.exists(clip_path) and os.path.getsize(clip_path) > 1024:
                    clips.append(clip_path)
                    logger.info(f"[BrollMatcher] 下载B-roll: {keyword} → {clip_path}")

            except Exception as e:
                logger.warning(f"[BrollMatcher] 下载失败 '{keyword}': {e}")

        return clips

    @staticmethod
    def _pick_best_file(video_files: list) -> Optional[str]:
        """选择最合适的视频文件（优先720p以下）"""
        candidates = []
        for vf in video_files:
            height = vf.get("height", 0)
            link = vf.get("link", "")
            if link and height <= 720:
                candidates.append((height, link))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # Fallback to any file
        for vf in video_files:
            if vf.get("link"):
                return vf["link"]
        return None
