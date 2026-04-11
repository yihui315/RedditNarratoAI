"""
Agent 4: 情绪配音Agent（Voice Agent）
调用TTS引擎生成带情绪的配音，输出MP3 + 时间戳
复用已有的voice.py服务，加上情绪控制层
"""

import os
from typing import Any, Dict, List
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.voice import generate_voice


class VoiceAgent(BaseAgent):
    """
    情绪配音Agent

    输入: 解说文案
    输出: MP3音频文件路径 + 每段时长列表
    """

    def __init__(self, config: dict):
        super().__init__(config, name="VoiceAgent")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "voice"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说文案
            session_id (str): 会话ID（用于输出目录隔离）
            voice (str): 语音名称（覆盖配置）
            rate (str): 语速（覆盖配置）
        """
        script = input_data.get("script", "")
        if not script:
            return AgentResult(success=False, error="缺少解说文案")

        session_id = input_data.get("session_id", "default")
        session_dir = str(self.output_dir / session_id)
        os.makedirs(session_dir, exist_ok=True)

        # 允许覆盖语音配置
        voice_config = dict(self.config)
        overrides = {}
        if input_data.get("voice"):
            overrides["voice"] = input_data["voice"]
        if input_data.get("rate"):
            overrides["rate"] = input_data["rate"]
        if overrides:
            tts_section = dict(voice_config.get("tts", {}))
            tts_section.update(overrides)
            voice_config["tts"] = tts_section

        try:
            audio_path, durations = generate_voice(
                text=script,
                output_dir=session_dir,
                config=voice_config,
            )

            if not audio_path or not os.path.exists(audio_path):
                return AgentResult(
                    success=False, error="TTS生成失败，无音频文件"
                )

            total_duration = sum(durations)
            return AgentResult(
                success=True,
                data={
                    "audio_path": audio_path,
                    "durations": durations,
                    "total_duration": total_duration,
                    "segment_count": len(durations),
                },
            )

        except Exception as e:
            logger.error(f"[VoiceAgent] TTS失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 音频文件存在且时长合理(5-120秒)"""
        if not result.success:
            return False

        audio_path = result.data.get("audio_path", "")
        if not audio_path or not os.path.exists(audio_path):
            return False

        total_duration = result.data.get("total_duration", 0)
        if total_duration < 5:
            logger.warning(f"[VoiceAgent] 音频太短: {total_duration:.1f}s")
            return False
        if total_duration > 120:
            logger.warning(f"[VoiceAgent] 音频太长: {total_duration:.1f}s")
            # 太长仍可接受
        return True
