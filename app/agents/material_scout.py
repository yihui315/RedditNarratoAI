"""
Agent 1: 素材识别Agent（Material Scout）
自动发现高潜力短剧素材：YouTube搜索 + 字幕/视频下载

支持两种模式:
  - YouTube搜索模式: 关键词搜索高播放量短剧
  - 手动URL模式: 直接传入视频URL列表
"""

import os
import json
import subprocess
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class MaterialScoutAgent(BaseAgent):
    """
    素材识别Agent

    输入: 搜索关键词 或 视频URL列表
    输出: 视频元信息 + 本地字幕/视频文件路径
    """

    def __init__(self, config: dict):
        super().__init__(config, name="MaterialScout")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "materials"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        yt_cfg = config.get("youtube", {})
        self.max_results = yt_cfg.get("max_results", 5)
        self.min_views = yt_cfg.get("min_views", 500_000)
        self.search_period = yt_cfg.get("search_period", "7d")
        self.language = yt_cfg.get("subtitle_language", "zh")

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            keywords (str): YouTube搜索关键词 (e.g. "short drama revenge")
            urls (list[str]): 直接指定视频URL
            max_results (int): 覆盖默认最大结果数
        """
        urls: List[str] = input_data.get("urls", [])
        keywords: str = input_data.get("keywords", "")
        max_results: int = input_data.get("max_results", self.max_results)

        if not urls and not keywords:
            return AgentResult(
                success=False,
                error="必须提供 keywords 或 urls",
            )

        # Step 1: 搜索（如果没有直接提供URL）
        if not urls and keywords:
            urls = self._search_youtube(keywords, max_results)
            if not urls:
                return AgentResult(
                    success=False,
                    error=f"未找到符合条件的视频: {keywords}",
                )

        # Step 2: 逐个下载元信息 + 字幕
        materials: List[Dict[str, Any]] = []
        for url in urls[:max_results]:
            try:
                info = self._download_material(url)
                if info:
                    materials.append(info)
            except Exception as e:
                logger.warning(f"下载素材失败 {url}: {e}")

        if not materials:
            return AgentResult(
                success=False,
                error="所有素材下载失败",
            )

        return AgentResult(
            success=True,
            data={
                "materials": materials,
                "count": len(materials),
                "keywords": keywords,
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 至少有1条素材且每条有字幕或视频文件"""
        if not result.success:
            return False
        materials = result.data.get("materials", [])
        if not materials:
            return False
        for m in materials:
            has_subtitle = m.get("subtitle_path") and os.path.exists(
                m["subtitle_path"]
            )
            has_video = m.get("video_path") and os.path.exists(m["video_path"])
            if not (has_subtitle or has_video):
                return False
        return True

    # ------------------------------------------------------------------
    # YouTube search via yt-dlp (no API key needed)
    # ------------------------------------------------------------------

    def _search_youtube(self, keywords: str, max_results: int) -> List[str]:
        """用yt-dlp搜索YouTube视频并筛选"""
        logger.info(f"[MaterialScout] 搜索YouTube: {keywords}")
        try:
            cmd = [
                "yt-dlp",
                f"ytsearch{max_results * 3}:{keywords}",
                "--dump-json",
                "--flat-playlist",
                "--no-download",
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                logger.error(f"yt-dlp 搜索失败: {proc.stderr[:500]}")
                return []

            urls: List[str] = []
            for line in proc.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                view_count = entry.get("view_count") or 0
                if view_count >= self.min_views:
                    video_id = entry.get("id", "")
                    if video_id:
                        urls.append(f"https://www.youtube.com/watch?v={video_id}")

                if len(urls) >= max_results:
                    break

            logger.info(
                f"[MaterialScout] 找到 {len(urls)} 个符合条件的视频"
            )
            return urls

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp 搜索超时")
            return []
        except FileNotFoundError:
            logger.error("yt-dlp 未安装，请先 pip install yt-dlp")
            return []

    # ------------------------------------------------------------------
    # Download material (subtitle + optional video)
    # ------------------------------------------------------------------

    def _download_material(self, url: str) -> Optional[Dict[str, Any]]:
        """下载单个视频的元信息、字幕和视频文件"""
        logger.info(f"[MaterialScout] 下载素材: {url}")

        # 1) 获取视频元信息
        info = self._get_video_info(url)
        if not info:
            return None

        video_id = info.get("id", "unknown")
        material_dir = self.output_dir / video_id
        material_dir.mkdir(parents=True, exist_ok=True)

        # 保存元信息
        info_path = str(material_dir / "info.json")
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

        # 2) 下载字幕
        subtitle_path = self._download_subtitles(url, material_dir, video_id)

        # 3) 下载视频（低分辨率用于剪辑）
        video_path = self._download_video(url, material_dir, video_id)

        return {
            "video_id": video_id,
            "title": info.get("title", ""),
            "url": url,
            "view_count": info.get("view_count", 0),
            "duration": info.get("duration", 0),
            "description": (info.get("description") or "")[:500],
            "info_path": info_path,
            "subtitle_path": subtitle_path or "",
            "video_path": video_path or "",
        }

    def _get_video_info(self, url: str) -> Optional[dict]:
        """获取视频元信息（不下载）"""
        try:
            cmd = ["yt-dlp", "--dump-json", "--no-download", url]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout.strip())
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
        return None

    def _download_subtitles(
        self, url: str, out_dir: Path, video_id: str
    ) -> Optional[str]:
        """下载字幕（自动字幕/手动字幕）"""
        sub_path = str(out_dir / f"{video_id}")
        try:
            cmd = [
                "yt-dlp",
                "--write-subs",
                "--write-auto-subs",
                f"--sub-langs={self.language}",
                "--sub-format=srt",
                "--skip-download",
                "-o", sub_path,
                url,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            # 查找生成的字幕文件
            for ext in [".srt", f".{self.language}.srt", f".{self.language}.vtt"]:
                candidate = str(out_dir / f"{video_id}{ext}")
                if os.path.exists(candidate):
                    logger.info(f"[MaterialScout] 字幕已下载: {candidate}")
                    return candidate

        except Exception as e:
            logger.warning(f"字幕下载失败: {e}")
        return None

    def _download_video(
        self, url: str, out_dir: Path, video_id: str
    ) -> Optional[str]:
        """下载低分辨率视频用于后续剪辑"""
        video_path = str(out_dir / f"{video_id}.mp4")
        try:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
                "--merge-output-format=mp4",
                "-o", video_path,
                url,
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if proc.returncode == 0 and os.path.exists(video_path):
                logger.info(f"[MaterialScout] 视频已下载: {video_path}")
                return video_path
        except Exception as e:
            logger.warning(f"视频下载失败: {e}")
        return None
