"""
背景音乐情绪匹配服务
根据段落情绪标签自动选择和混合 BGM
"""

import os
import re
import random
from pathlib import Path
from typing import Optional, List, Dict
from loguru import logger


# 情绪标签到 BGM 目录的映射
MOOD_DIRS = {
    "tense": "tense",
    "emotional": "emotional",
    "upbeat": "upbeat",
    "calm": "calm",
}

# 支持的音频格式
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


class BGMService:
    """
    背景音乐情绪匹配服务

    功能:
    - 根据情绪标签从 resource/bgm/{mood}/ 选择 BGM
    - 自动调整音量（不盖过语音）
    - 段落切换时 crossfade
    """

    def __init__(self, config: dict):
        self.config = config
        bgm_config = config.get("bgm", {})
        self.enabled = bgm_config.get("enabled", True)
        self.volume = bgm_config.get("volume", 0.15)
        self.crossfade_duration = bgm_config.get("crossfade_duration", 1.0)

        # BGM 资源目录
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.realpath(__file__)
        )))
        self.bgm_dir = Path(root_dir) / "resource" / "bgm"

    def get_bgm_for_mood(self, mood: str) -> Optional[str]:
        """
        根据情绪标签获取 BGM 文件路径

        Args:
            mood: 情绪标签 (tense/emotional/upbeat/calm)

        Returns:
            str: BGM 文件路径，无匹配返回 None
        """
        if not self.enabled:
            return None

        mood_dir_name = MOOD_DIRS.get(mood, "calm")
        mood_dir = self.bgm_dir / mood_dir_name

        if not mood_dir.exists():
            logger.debug(f"BGM 目录不存在: {mood_dir}")
            return None

        # 获取该情绪目录下所有音频文件
        audio_files = [
            f for f in mood_dir.iterdir()
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]

        if not audio_files:
            logger.debug(f"BGM 目录为空: {mood_dir}")
            return None

        # 随机选择一个
        chosen = random.choice(audio_files)
        logger.info(f"BGM 选择: [{mood}] → {chosen.name}")
        return str(chosen)

    def get_bgm_for_timeline(self, timeline: List[dict]) -> List[Optional[str]]:
        """
        为整个时间轴选择 BGM

        Args:
            timeline: 时间轴 [{text, start_ms, end_ms, mood}, ...]

        Returns:
            List[Optional[str]]: 每段对应的 BGM 文件路径
        """
        results = []
        last_mood = None
        last_bgm = None

        for segment in timeline:
            mood = segment.get("mood", "calm")
            if mood == last_mood and last_bgm:
                # 同一情绪复用同一 BGM（连贯性）
                results.append(last_bgm)
            else:
                bgm = self.get_bgm_for_mood(mood)
                results.append(bgm)
                last_mood = mood
                last_bgm = bgm

        return results

    def create_bgm_track(
        self,
        timeline: List[dict],
        total_duration_ms: int,
        output_path: str
    ) -> Optional[str]:
        """
        创建完整的 BGM 音轨（拼接 + crossfade + 音量调整）

        Args:
            timeline: 时间轴
            total_duration_ms: 总时长（毫秒）
            output_path: 输出文件路径

        Returns:
            str: 输出文件路径，失败返回 None
        """
        if not self.enabled:
            return None

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub 未安装，跳过 BGM 生成")
            return None

        bgm_files = self.get_bgm_for_timeline(timeline)

        # 过滤有效的 BGM
        if not any(bgm_files):
            logger.info("无可用 BGM 文件，跳过 BGM 轨道")
            return None

        try:
            # 创建空白音轨
            combined = AudioSegment.silent(duration=total_duration_ms)
            volume_db = 20 * (self.volume ** 0.5) - 20  # 线性音量转 dB

            for i, (segment, bgm_path) in enumerate(zip(timeline, bgm_files)):
                if not bgm_path or not os.path.exists(bgm_path):
                    continue

                start_ms = segment.get("start_ms", 0)
                end_ms = segment.get("end_ms", start_ms + 5000)
                segment_duration = end_ms - start_ms

                # 加载 BGM 并调整时长
                bgm = AudioSegment.from_file(bgm_path)
                bgm = bgm + volume_db  # 调整音量

                # 循环 BGM 以覆盖段落时长
                if len(bgm) < segment_duration:
                    repeats = (segment_duration // len(bgm)) + 1
                    bgm = bgm * repeats
                bgm = bgm[:segment_duration]

                # 淡入淡出
                fade_ms = min(int(self.crossfade_duration * 1000), segment_duration // 4)
                if fade_ms > 0:
                    bgm = bgm.fade_in(fade_ms).fade_out(fade_ms)

                # 叠加到总音轨
                combined = combined.overlay(bgm, position=start_ms)

            # 导出
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            combined.export(output_path, format="mp3")
            logger.info(f"BGM 音轨生成: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"BGM 音轨生成失败: {e}")
            return None


def parse_mood_tags(script: str) -> List[str]:
    """
    从文案中解析情绪标签

    Args:
        script: 带 [mood:xxx] 标注的文案

    Returns:
        List[str]: 每段的情绪标签
    """
    paragraphs = [p.strip() for p in script.split('---') if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in script.split('\n') if p.strip()]

    moods = []
    for para in paragraphs:
        match = re.search(r'\[mood:(\w+)\]', para)
        moods.append(match.group(1) if match else "calm")

    return moods
