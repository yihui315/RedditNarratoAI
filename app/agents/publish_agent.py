"""
Agent 9: 自动发布Agent（Publish Agent）
支持自动发布到TikTok/YouTube Shorts/Instagram Reels
当前版本提供发布框架 + 元数据准备，实际API集成可按需扩展
"""

import os
import json
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class PublishAgent(BaseAgent):
    """
    自动发布Agent

    输入: 视频路径 + SEO元数据
    输出: 各平台发布状态
    """

    def __init__(self, config: dict):
        super().__init__(config, name="PublishAgent")
        publish_cfg = config.get("publish", {})
        self.auto_publish = publish_cfg.get("auto_publish", False)
        self.platforms = publish_cfg.get("platforms", [])
        self.tiktok_token = publish_cfg.get("tiktok_access_token", "") or os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.youtube_api_key = publish_cfg.get("youtube_api_key", "") or os.getenv("YOUTUBE_API_KEY", "")

        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "publish"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            video_path (str): 视频文件路径
            seo (dict): SEO元数据
            session_id (str): 会话ID
        """
        video_path = input_data.get("video_path", "")
        seo = input_data.get("seo", {})
        session_id = input_data.get("session_id", "default")

        if not video_path or not os.path.exists(video_path):
            return AgentResult(success=False, error=f"视频文件不存在: {video_path}")

        publish_results: Dict[str, Any] = {}
        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        if not self.auto_publish:
            # Save publish-ready package for manual upload
            package = self._prepare_publish_package(video_path, seo, session_dir)
            return AgentResult(
                success=True,
                data={
                    "auto_publish": False,
                    "package_path": package,
                    "platforms": self.platforms,
                    "message": "自动发布未开启，已准备发布包",
                },
            )

        # Auto-publish to each platform
        for platform in self.platforms:
            try:
                result = self._publish_to_platform(platform, video_path, seo)
                publish_results[platform] = result
            except Exception as e:
                logger.error(f"[PublishAgent] 发布到{platform}失败: {e}")
                publish_results[platform] = {
                    "success": False,
                    "error": str(e),
                }

        # Save publish log
        log_path = str(session_dir / "publish_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(publish_results, f, ensure_ascii=False, indent=2)

        success_count = sum(
            1 for r in publish_results.values()
            if isinstance(r, dict) and r.get("success")
        )

        return AgentResult(
            success=True,
            data={
                "auto_publish": True,
                "results": publish_results,
                "success_count": success_count,
                "total_platforms": len(self.platforms),
                "log_path": log_path,
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 发布包已准备或至少一个平台发布成功"""
        if not result.success:
            return False
        if not result.data.get("auto_publish"):
            # Manual mode - check package exists
            return bool(result.data.get("package_path"))
        # Auto mode - at least one success
        return result.data.get("success_count", 0) > 0

    # ------------------------------------------------------------------
    # Platform publish methods
    # ------------------------------------------------------------------

    def _publish_to_platform(
        self, platform: str, video_path: str, seo: dict
    ) -> dict:
        """发布到指定平台"""
        if platform == "tiktok":
            return self._publish_tiktok(video_path, seo)
        elif platform in ("youtube_shorts", "youtube"):
            return self._publish_youtube(video_path, seo)
        elif platform in ("instagram_reels", "instagram"):
            return self._publish_instagram(video_path, seo)
        else:
            return {"success": False, "error": f"不支持的平台: {platform}"}

    def _publish_tiktok(self, video_path: str, seo: dict) -> dict:
        """发布到TikTok（需要TikTok API access token）"""
        if not self.tiktok_token:
            return {"success": False, "error": "未配置TikTok access token"}

        logger.info("[PublishAgent] 准备发布到TikTok...")
        # TikTok Content Posting API v2 framework
        # Actual implementation requires OAuth2 flow + file upload
        # This is a placeholder for the API integration
        return {
            "success": False,
            "error": "TikTok API集成待完善（需要OAuth2授权流程）",
            "title": seo.get("seo_title", ""),
            "tags": seo.get("hashtags", []),
        }

    def _publish_youtube(self, video_path: str, seo: dict) -> dict:
        """发布到YouTube Shorts（需要YouTube Data API v3）"""
        if not self.youtube_api_key:
            return {"success": False, "error": "未配置YouTube API Key"}

        logger.info("[PublishAgent] 准备发布到YouTube Shorts...")
        # YouTube Data API v3 upload framework
        return {
            "success": False,
            "error": "YouTube API集成待完善（需要OAuth2授权流程）",
            "title": seo.get("seo_title", ""),
            "description": seo.get("description", ""),
            "tags": seo.get("tags", []),
        }

    def _publish_instagram(self, video_path: str, seo: dict) -> dict:
        """发布到Instagram Reels（需要Instagram Graph API）"""
        logger.info("[PublishAgent] 准备发布到Instagram Reels...")
        return {
            "success": False,
            "error": "Instagram API集成待完善（需要Business Account + Graph API）",
        }

    # ------------------------------------------------------------------
    # Publish package (for manual upload)
    # ------------------------------------------------------------------

    def _prepare_publish_package(
        self, video_path: str, seo: dict, output_dir: Path
    ) -> str:
        """准备发布包：视频 + 元数据 + 缩略图建议"""
        package_path = str(output_dir / "publish_package.json")

        package = {
            "video_path": video_path,
            "seo": seo,
            "platforms": self.platforms,
            "ready_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "instructions": {
                "tiktok": "上传视频 → 粘贴标题和标签 → 发布",
                "youtube_shorts": "上传为YouTube Shorts → 填写标题/描述/标签",
                "instagram_reels": "上传为Reels → 添加描述和标签",
            },
        }

        with open(package_path, "w", encoding="utf-8") as f:
            json.dump(package, f, ensure_ascii=False, indent=2)

        logger.info(f"[PublishAgent] 发布包已准备: {package_path}")
        return package_path
