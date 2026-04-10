"""
转场效果引擎
段落切换时添加视觉转场效果
"""

from typing import Optional
from loguru import logger

try:
    from moviepy import (
        VideoFileClip,
        ColorClip,
        CompositeVideoClip,
        concatenate_videoclips,
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger.warning("moviepy 未安装，转场效果不可用")


# 支持的转场类型
TRANSITION_TYPES = {"crossfade", "fade_to_black", "slide_left", "none"}


class TransitionService:
    """
    转场效果服务

    支持:
    - crossfade: 淡入淡出交叉（默认）
    - fade_to_black: 淡入黑屏再淡出
    - slide_left: 左滑切换
    - none: 无转场
    """

    def __init__(self, config: dict):
        self.config = config
        transition_config = config.get("transition", {})
        self.enabled = transition_config.get("enabled", True)
        self.transition_type = transition_config.get("type", "crossfade")
        self.duration = transition_config.get("duration", 0.5)

        if self.transition_type not in TRANSITION_TYPES:
            logger.warning(
                f"未知转场类型: {self.transition_type}，使用 crossfade"
            )
            self.transition_type = "crossfade"

    def apply_transition(self, clip1, clip2):
        """
        在两个视频片段之间添加转场效果

        Args:
            clip1: 前一个视频片段 (moviepy clip)
            clip2: 后一个视频片段 (moviepy clip)

        Returns:
            moviepy clip: 带转场的合并片段
        """
        if not self.enabled or not MOVIEPY_AVAILABLE:
            return concatenate_videoclips([clip1, clip2])

        if self.transition_type == "none":
            return concatenate_videoclips([clip1, clip2])

        try:
            if self.transition_type == "crossfade":
                return self._crossfade(clip1, clip2)
            elif self.transition_type == "fade_to_black":
                return self._fade_to_black(clip1, clip2)
            elif self.transition_type == "slide_left":
                return self._slide_left(clip1, clip2)
            else:
                return concatenate_videoclips([clip1, clip2])
        except Exception as e:
            logger.warning(f"转场效果失败: {e}，使用直接拼接")
            return concatenate_videoclips([clip1, clip2])

    def apply_transitions_to_clips(self, clips: list):
        """
        为一组视频片段依次添加转场

        Args:
            clips: moviepy clip 列表

        Returns:
            moviepy clip: 合并后的视频
        """
        if not clips:
            return None

        if len(clips) == 1:
            return clips[0]

        if not self.enabled or not MOVIEPY_AVAILABLE:
            return concatenate_videoclips(clips)

        try:
            if self.transition_type == "crossfade" and self.duration > 0:
                # MoviePy crossfade 通过设置 start 实现重叠
                return concatenate_videoclips(
                    clips, method="compose", padding=-self.duration
                )
            elif self.transition_type == "fade_to_black":
                # 每段添加淡入淡出
                processed = []
                fade_dur = min(self.duration, 0.5)
                for clip in clips:
                    if clip.duration > fade_dur * 2:
                        clip = clip.crossfadein(fade_dur).crossfadeout(fade_dur)
                    processed.append(clip)
                return concatenate_videoclips(processed)
            else:
                return concatenate_videoclips(clips)
        except Exception as e:
            logger.warning(f"批量转场失败: {e}，使用直接拼接")
            return concatenate_videoclips(clips)

    def _crossfade(self, clip1, clip2):
        """淡入淡出交叉"""
        duration = min(self.duration, clip1.duration / 2, clip2.duration / 2)
        clip1 = clip1.crossfadeout(duration)
        clip2 = clip2.crossfadein(duration)
        return concatenate_videoclips(
            [clip1, clip2], method="compose", padding=-duration
        )

    def _fade_to_black(self, clip1, clip2):
        """通过黑屏过渡"""
        fade_dur = min(self.duration / 2, 0.3)
        clip1 = clip1.crossfadeout(fade_dur)
        clip2 = clip2.crossfadein(fade_dur)

        # 插入短暂黑屏
        black_dur = max(self.duration - fade_dur * 2, 0.1)
        black = ColorClip(
            size=clip1.size, color=(0, 0, 0), duration=black_dur
        )
        return concatenate_videoclips([clip1, black, clip2])

    def _slide_left(self, clip1, clip2):
        """左滑切换（简化版：实际用 crossfade 代替）"""
        # 完整的滑动效果需要逐帧处理，这里简化为快速 crossfade
        duration = min(self.duration, clip1.duration / 2, clip2.duration / 2)
        clip1 = clip1.crossfadeout(duration)
        clip2 = clip2.crossfadein(duration)
        return concatenate_videoclips(
            [clip1, clip2], method="compose", padding=-duration
        )
