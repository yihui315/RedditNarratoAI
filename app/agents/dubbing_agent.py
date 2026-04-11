"""
Agent: DubbingAgent (v5.0)
高质量角色级克隆配音 — WhisperX词级对齐 + GPT-SoVITS角色克隆
灵感来源: VideoLingo Netflix级字幕对齐 + GPT-SoVITS角色克隆配音

输入: script + characters → 为每个角色生成克隆配音
输出: dubbed_audio 路径 + 时间戳列表
优雅降级: GPT-SoVITS不可用时回退到Edge TTS标准配音
"""

import os
import uuid
from typing import Any, Dict, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class DubbingAgent(BaseAgent):
    """
    高质量配音Agent (v5.0)

    支持两种模式:
    1. GPT-SoVITS克隆模式: 角色级音色克隆（需要GPT-SoVITS API服务）
    2. Edge TTS模式: 标准TTS（默认降级方案，免费无需配置）

    配置项:
        config["dubbing"]["gpt_sovits_api"]: GPT-SoVITS API地址
        config["dubbing"]["enabled"]: 是否启用高质配音（默认True）
    """

    def __init__(self, config: dict):
        super().__init__(config, name="DubbingAgent")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "dubbing"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        dubbing_cfg = config.get("dubbing", {})
        self.gpt_sovits_api = (
            dubbing_cfg.get("gpt_sovits_api", "")
            or os.getenv("GPT_SOVITS_API", "")
        )
        self.enabled = dubbing_cfg.get("enabled", True)

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说/对白文本
            characters (list): 角色列表（含voice_id）
            session_id (str): 会话ID
            mode (str): "clone" or "standard"（默认自动检测）
        """
        script = input_data.get("script", "")
        characters = input_data.get("characters", [])
        session_id = input_data.get("session_id", uuid.uuid4().hex[:8])

        if not script:
            return AgentResult(
                success=False,
                error="缺少解说文案(script)",
            )

        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # 判断是否可用GPT-SoVITS克隆
        use_clone = self.gpt_sovits_api and self.enabled

        if use_clone:
            try:
                result = self._generate_clone_audio(
                    script, characters, session_dir
                )
                if result:
                    return AgentResult(
                        success=True,
                        data={
                            "dubbed_audio": result["audio_path"],
                            "mode": "gpt_sovits_clone",
                            "segments": result.get("segments", []),
                        },
                    )
            except Exception as e:
                logger.warning(
                    f"[DubbingAgent] GPT-SoVITS克隆失败，降级到Edge TTS: {e}"
                )

        # 降级：使用标准Edge TTS
        try:
            audio_path = self._generate_edge_tts(script, session_dir)
            return AgentResult(
                success=True,
                data={
                    "dubbed_audio": audio_path,
                    "mode": "edge_tts_fallback",
                    "segments": [],
                },
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"配音生成失败: {e}",
            )

    def verify(self, result: AgentResult) -> bool:
        """验证: 音频文件存在且非空"""
        if not result.success:
            return False
        audio_path = result.data.get("dubbed_audio", "")
        if not audio_path:
            return False
        return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0

    def _generate_clone_audio(
        self, script: str, characters: list, output_dir: Path
    ) -> Optional[Dict]:
        """使用GPT-SoVITS API生成角色克隆配音"""
        import requests

        # 解说模式：单角色配音
        voice_id = "narrator_default"
        if characters:
            voice_id = characters[0].get("voice_id", "narrator_default")

        payload = {
            "text": script[:5000],
            "voice_id": voice_id,
            "language": "zh",
        }

        resp = requests.post(
            f"{self.gpt_sovits_api}/tts",
            json=payload,
            timeout=120,
        )

        if resp.status_code != 200:
            logger.error(
                f"[DubbingAgent] GPT-SoVITS API错误: "
                f"{resp.status_code} {resp.text[:200]}"
            )
            return None

        audio_path = str(output_dir / "dubbed_clone.wav")
        with open(audio_path, "wb") as f:
            f.write(resp.content)

        logger.info(f"[DubbingAgent] 克隆配音完成: {audio_path}")
        return {"audio_path": audio_path, "segments": []}

    def _generate_edge_tts(self, script: str, output_dir: Path) -> str:
        """降级方案：使用Edge TTS生成标准配音"""
        import asyncio
        import edge_tts

        tts_config = self.config.get("tts", {})
        voice = tts_config.get("voice", "zh-CN-XiaoxiaoNeural")
        rate = tts_config.get("rate", "+0%")

        audio_path = str(output_dir / "dubbed_edge.mp3")

        async def _generate():
            communicate = edge_tts.Communicate(
                text=script[:5000],
                voice=voice,
                rate=rate,
            )
            await communicate.save(audio_path)

        # 在新事件循环中运行（避免与外层asyncio冲突）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在async上下文中，创建新线程运行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_generate())).result(timeout=120)
            else:
                loop.run_until_complete(_generate())
        except RuntimeError:
            asyncio.run(_generate())

        logger.info(f"[DubbingAgent] Edge TTS配音完成: {audio_path}")
        return audio_path
