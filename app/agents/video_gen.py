"""
Agent 6: AI视频生成Agent（Video Gen）
支持三种模式:
  - moviepy: 本地MoviePy合成（默认，无需API Key）
  - kling: 快影 Kling API text-to-video
  - runway: Runway Gen-3 API text-to-video

当配置了Kling/Runway API Key时自动升级为AI生成模式
"""

import os
import time
from typing import Any, Dict, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class VideoGenAgent(BaseAgent):
    """
    AI视频生成Agent

    输入: 脚本文本 + 模式选择
    输出: 生成的视频片段路径列表
    """

    # Supported modes
    MODE_MOVIEPY = "moviepy"
    MODE_KLING = "kling"
    MODE_RUNWAY = "runway"

    def __init__(self, config: dict):
        super().__init__(config, name="VideoGen")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "video_gen"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        vg_cfg = config.get("video_gen", {})
        self.kling_api_key = vg_cfg.get("kling_api_key", "") or os.getenv("KLING_API_KEY", "")
        self.runway_api_key = vg_cfg.get("runway_api_key", "") or os.getenv("RUNWAY_API_KEY", "")

        # Auto-detect mode based on available API keys
        if vg_cfg.get("mode"):
            self.mode = vg_cfg["mode"]
        elif self.kling_api_key:
            self.mode = self.MODE_KLING
        elif self.runway_api_key:
            self.mode = self.MODE_RUNWAY
        else:
            self.mode = self.MODE_MOVIEPY

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说文案（用于生成视频的提示词）
            session_id (str): 会话ID
            duration (int): 目标视频时长（秒）
            style (str): 视觉风格描述（可选）
        """
        script = input_data.get("script", "")
        session_id = input_data.get("session_id", "default")
        duration = input_data.get("duration", 60)
        style = input_data.get("style", "cinematic, dramatic lighting")

        if not script:
            return AgentResult(success=False, error="缺少脚本文案")

        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        try:
            if self.mode == self.MODE_KLING:
                video_path = self._generate_kling(script, style, duration, session_dir)
            elif self.mode == self.MODE_RUNWAY:
                video_path = self._generate_runway(script, style, duration, session_dir)
            else:
                # MoviePy fallback - pass through, actual video created by VideoEditor
                video_path = ""
                return AgentResult(
                    success=True,
                    data={
                        "mode": self.MODE_MOVIEPY,
                        "video_clips": [],
                        "message": "MoviePy模式：跳过AI视频生成，由VideoEditor直接合成",
                    },
                )

            return AgentResult(
                success=True,
                data={
                    "mode": self.mode,
                    "video_path": video_path or "",
                    "video_clips": [video_path] if video_path else [],
                    "duration": duration,
                },
            )

        except Exception as e:
            logger.error(f"[VideoGen] 视频生成失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: MoviePy模式直接通过; AI模式检查文件存在"""
        if not result.success:
            return False
        mode = result.data.get("mode", self.MODE_MOVIEPY)
        if mode == self.MODE_MOVIEPY:
            return True  # pass-through mode always valid
        video_clips = result.data.get("video_clips", [])
        return len(video_clips) > 0 and all(
            os.path.exists(p) for p in video_clips
        )

    # ------------------------------------------------------------------
    # Kling API
    # ------------------------------------------------------------------

    def _generate_kling(
        self, script: str, style: str, duration: int, output_dir: Path
    ) -> Optional[str]:
        """使用Kling API生成视频（需要KLING_API_KEY）"""
        import requests

        prompt = f"{style}. Scene: {script[:200]}"
        logger.info(f"[VideoGen] Kling生成中: {prompt[:80]}...")

        headers = {
            "Authorization": f"Bearer {self.kling_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "duration": min(duration, 10),  # Kling max 10s per clip
            "aspect_ratio": "16:9",
        }

        resp = requests.post(
            "https://api.klingai.com/v1/videos/text2video",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"[VideoGen] Kling API错误: {resp.status_code} {resp.text[:200]}")
            return None

        task_id = resp.json().get("data", {}).get("task_id")
        if not task_id:
            logger.error("[VideoGen] Kling未返回task_id")
            return None

        # Poll for completion (max 5 minutes)
        video_url = self._poll_kling_task(task_id, headers, timeout=300)
        if not video_url:
            return None

        # Download video
        output_path = str(output_dir / "kling_output.mp4")
        video_resp = requests.get(video_url, timeout=120)
        with open(output_path, "wb") as f:
            f.write(video_resp.content)

        logger.info(f"[VideoGen] Kling视频已下载: {output_path}")
        return output_path

    def _poll_kling_task(
        self, task_id: str, headers: dict, timeout: int = 300
    ) -> Optional[str]:
        """轮询Kling任务状态"""
        import requests

        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(
                f"https://api.klingai.com/v1/videos/text2video/{task_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                status = data.get("task_status", "")
                if status == "succeed":
                    works = data.get("task_result", {}).get("videos", [])
                    if works:
                        return works[0].get("url")
                elif status == "failed":
                    logger.error(f"[VideoGen] Kling任务失败: {data.get('task_status_msg')}")
                    return None
            time.sleep(10)

        logger.error("[VideoGen] Kling任务超时")
        return None

    # ------------------------------------------------------------------
    # Runway API
    # ------------------------------------------------------------------

    def _generate_runway(
        self, script: str, style: str, duration: int, output_dir: Path
    ) -> Optional[str]:
        """使用Runway Gen-3 API生成视频（需要RUNWAY_API_KEY）"""
        import requests

        prompt = f"{style}. Scene: {script[:200]}"
        logger.info(f"[VideoGen] Runway生成中: {prompt[:80]}...")

        headers = {
            "Authorization": f"Bearer {self.runway_api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }
        payload = {
            "promptText": prompt,
            "model": "gen3a_turbo",
            "duration": min(duration, 10),
            "ratio": "16:9",
        }

        resp = requests.post(
            "https://api.dev.runwayml.com/v1/text_to_video",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"[VideoGen] Runway API错误: {resp.status_code} {resp.text[:200]}")
            return None

        task_id = resp.json().get("id")
        if not task_id:
            return None

        # Poll for completion
        video_url = self._poll_runway_task(task_id, headers, timeout=300)
        if not video_url:
            return None

        output_path = str(output_dir / "runway_output.mp4")
        video_resp = requests.get(video_url, timeout=120)
        with open(output_path, "wb") as f:
            f.write(video_resp.content)

        logger.info(f"[VideoGen] Runway视频已下载: {output_path}")
        return output_path

    def _poll_runway_task(
        self, task_id: str, headers: dict, timeout: int = 300
    ) -> Optional[str]:
        """轮询Runway任务状态"""
        import requests

        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status == "SUCCEEDED":
                    output = data.get("output", [])
                    if output:
                        return output[0]
                elif status == "FAILED":
                    logger.error(f"[VideoGen] Runway任务失败: {data.get('failure')}")
                    return None
            time.sleep(10)

        logger.error("[VideoGen] Runway任务超时")
        return None
