"""
B-roll 自动匹配服务
支持 Pexels API 视频搜索下载 + 本地 stock 降级方案
"""

import os
import re
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPX_AVAILABLE = False


class BRollService:
    """
    B-roll 视频获取服务

    优先级:
    1. Pexels API 在线搜索下载
    2. 本地 resource/videos/ 目录匹配
    3. 返回 None（使用纯色背景降级）
    """

    def __init__(self, config: dict):
        self.config = config
        broll_config = config.get("broll", {})
        self.enabled = broll_config.get("enabled", True)
        self.pexels_api_key = broll_config.get("pexels_api_key", "")
        # Sanitize paths from config to prevent path traversal
        cache_dir_raw = broll_config.get("cache_dir", "./cache/broll")
        self.cache_dir = Path(cache_dir_raw).resolve()
        local_video_raw = config.get("video_background", {}).get(
            "local_video_path", "./resource/videos"
        )
        self.local_video_dir = Path(local_video_raw).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_broll_for_segment(
        self,
        keywords: List[str],
        duration: float,
        width: int = 1920,
        height: int = 1080
    ) -> Optional[str]:
        """
        为单个段落获取 B-roll 视频

        Args:
            keywords: 搜索关键词列表
            duration: 需要的视频时长（秒）
            width: 视频宽度
            height: 视频高度

        Returns:
            str: 视频文件路径，失败返回 None
        """
        if not self.enabled:
            return None

        for keyword in keywords:
            # 1. 检查缓存
            cached = self._check_cache(keyword)
            if cached:
                logger.debug(f"B-roll 缓存命中: {keyword} → {cached}")
                return cached

            # 2. 尝试 Pexels API
            if self.pexels_api_key and HTTPX_AVAILABLE:
                path = self._search_pexels(keyword, width, height)
                if path:
                    return path

            # 3. 本地匹配
            path = self._search_local(keyword)
            if path:
                return path

        logger.warning(f"B-roll 未找到匹配: {keywords}")
        return None

    def get_broll_for_timeline(
        self,
        timeline: List[dict],
        width: int = 1920,
        height: int = 1080
    ) -> List[Optional[str]]:
        """
        为整个时间轴获取 B-roll 视频列表

        Args:
            timeline: 时间轴 [{text, start_ms, end_ms, mood, broll_keywords}, ...]

        Returns:
            List[Optional[str]]: 每段对应的视频路径
        """
        results = []
        for segment in timeline:
            keywords = segment.get("broll_keywords", [])
            if not keywords:
                results.append(None)
                continue

            duration = (segment.get("end_ms", 0) - segment.get("start_ms", 0)) / 1000
            path = self.get_broll_for_segment(keywords, duration, width, height)
            results.append(path)

        return results

    def _check_cache(self, keyword: str) -> Optional[str]:
        """检查本地缓存"""
        cache_key = hashlib.md5(keyword.encode()).hexdigest()[:12]
        for ext in [".mp4", ".webm", ".mov"]:
            cached_path = self.cache_dir / f"{cache_key}{ext}"
            if cached_path.exists() and cached_path.stat().st_size > 0:
                return str(cached_path)
        return None

    def _search_pexels(self, keyword: str, width: int, height: int) -> Optional[str]:
        """从 Pexels API 搜索并下载视频"""
        if not HTTPX_AVAILABLE:
            return None

        try:
            headers = {"Authorization": self.pexels_api_key}
            # 根据宽高比选择方向
            orientation = "landscape" if width >= height else "portrait"

            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    "https://api.pexels.com/videos/search",
                    params={
                        "query": keyword,
                        "per_page": 3,
                        "orientation": orientation,
                        "size": "medium",
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            videos = data.get("videos", [])
            if not videos:
                logger.debug(f"Pexels 无结果: {keyword}")
                return None

            # 选择第一个可用视频
            for video in videos:
                video_files = video.get("video_files", [])
                # 优先选择 HD 质量
                for vf in sorted(video_files, key=lambda x: x.get("height", 0), reverse=True):
                    if vf.get("height", 0) >= 720:
                        download_url = vf.get("link", "")
                        if download_url:
                            return self._download_video(keyword, download_url)

            return None

        except Exception as e:
            logger.warning(f"Pexels API 请求失败: {e}")
            return None

    def _download_video(self, keyword: str, url: str) -> Optional[str]:
        """下载视频到缓存"""
        cache_key = hashlib.md5(keyword.encode()).hexdigest()[:12]
        ext = ".mp4"
        cached_path = self.cache_dir / f"{cache_key}{ext}"

        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with open(cached_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)

            logger.info(f"B-roll 下载完成: {keyword} → {cached_path}")
            return str(cached_path)

        except Exception as e:
            logger.warning(f"B-roll 下载失败: {e}")
            if cached_path.exists():
                cached_path.unlink()
            return None

    def _search_local(self, keyword: str) -> Optional[str]:
        """在本地视频目录中搜索匹配"""
        if not self.local_video_dir.exists():
            return None

        keyword_lower = keyword.lower().replace(" ", "_")
        keyword_parts = keyword.lower().split()

        for video_file in self.local_video_dir.iterdir():
            if video_file.suffix.lower() not in [".mp4", ".webm", ".mov", ".avi"]:
                continue

            filename = video_file.stem.lower()
            # 精确匹配或部分匹配
            if keyword_lower in filename:
                logger.debug(f"B-roll 本地匹配: {keyword} → {video_file}")
                return str(video_file)

            # 关键词部分匹配
            if any(part in filename for part in keyword_parts):
                logger.debug(f"B-roll 本地部分匹配: {keyword} → {video_file}")
                return str(video_file)

        return None


def parse_broll_tags(script: str) -> List[List[str]]:
    """
    从文案中解析 B-roll 标签

    Args:
        script: 带 [broll:xxx] 标注的文案

    Returns:
        List[List[str]]: 每段的 B-roll 关键词列表
    """
    paragraphs = [p.strip() for p in script.split('---') if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in script.split('\n') if p.strip()]

    results = []
    for para in paragraphs:
        tags = re.findall(r'\[broll:([^\]]+)\]', para)
        keywords = []
        for tag in tags:
            keywords.extend([k.strip() for k in tag.split(',')])
        results.append(keywords)

    return results
