import traceback
import numpy as np

# import pysrt
from typing import Optional
from typing import List
from loguru import logger
from moviepy import *
from PIL import ImageFont
from contextlib import contextmanager
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    CompositeAudioClip
)


from app.models import VideoAspect, SubtitlePosition


def wrap_text(text, max_width, font, fontsize=60):
    """
    文本自动换行处理
    Args:
        text: 待处理的文本
        max_width: 最大宽度
        font: 字体文件路径
        fontsize: 字体大小

    Returns:
        tuple: (换行后的文本, 文本高度)
    """
    # 创建字体对象
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    logger.debug(f"换行文本, 最大宽度: {max_width}, 文本宽度: {width}, 文本: {text}")

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        # logger.warning(f"wrapped text: {result}")
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    logger.debug(f"换行文本: {result}")
    return result, height


@contextmanager
def manage_clip(clip):
    """
    视频片段资源管理器
    Args:
        clip: 视频片段对象

    Yields:
        VideoFileClip: 视频片段对象
    """
    try:
        yield clip
    finally:
        clip.close()
        del clip


def resize_video_with_padding(clip, target_width: int, target_height: int):
    """
    调整视频尺寸并添加黑边
    Args:
        clip: 视频片段
        target_width: 目标宽度
        target_height: 目标高度

    Returns:
        CompositeVideoClip: 调整尺寸后的视频
    """
    clip_ratio = clip.w / clip.h
    target_ratio = target_width / target_height

    if clip_ratio == target_ratio:
        return clip.resize((target_width, target_height))

    if clip_ratio > target_ratio:
        scale_factor = target_width / clip.w
    else:
        scale_factor = target_height / clip.h

    new_width = int(clip.w * scale_factor)
    new_height = int(clip.h * scale_factor)
    clip_resized = clip.resize(newsize=(new_width, new_height))

    background = ColorClip(
        size=(target_width, target_height),
        color=(0, 0, 0)
    ).set_duration(clip.duration)

    return CompositeVideoClip([
        background,
        clip_resized.set_position("center")
    ])


def loop_audio_clip(audio_clip: AudioFileClip, target_duration: float) -> AudioFileClip:
    """
    循环音频片段直到达到目标时长

    参数:
        audio_clip: 原始音频片段
        target_duration: 目标时长（秒）
    返回:
        循环后的音频片段
    """
    # 计算需要循环的次数
    loops_needed = int(target_duration / audio_clip.duration) + 1

    # 创建足够长的音频
    extended_audio = audio_clip
    for _ in range(loops_needed - 1):
        extended_audio = CompositeAudioClip([
            extended_audio,
            audio_clip.set_start(extended_audio.duration)
        ])

    # 裁剪到目标时长
    return extended_audio.subclip(0, target_duration)


def calculate_subtitle_position(position, video_height: int, text_height: int = 0) -> tuple:
    """
    计算字幕在视频中的具体位置
    
    Args:
        position: 位置配置，可以是 SubtitlePosition 枚举值或表示距顶部百分比的浮点数
        video_height: 视频高度
        text_height: 字幕文本高度
    
    Returns:
        tuple: (x, y) 坐标
    """
    margin = 50  # 字幕距离边缘的边距
    
    if isinstance(position, (int, float)):
        # 百分比位置
        return ('center', int(video_height * position))
    
    # 预设位置
    if position == SubtitlePosition.TOP:
        return ('center', margin)
    elif position == SubtitlePosition.CENTER:
        return ('center', video_height // 2)
    elif position == SubtitlePosition.BOTTOM:
        return ('center', video_height - margin - text_height)
    
    # 默认底部
    return ('center', video_height - margin - text_height)


def generate_video_v3(
        video_path: str,
        subtitle_style: dict,
        volume_config: dict,
        subtitle_path: Optional[str] = None,
        bgm_path: Optional[str] = None,
        narration_path: Optional[str] = None,
        output_path: str = "output.mp4",
        font_path: Optional[str] = None,
        subtitle_enabled: bool = True
) -> None:
    """
    合并视频素材，包括视频、字幕、BGM和解说音频

    参数:
        video_path: 原视频文件路径
        subtitle_path: SRT字幕文件路径（可选）
        bgm_path: 背景音乐文件路径（可选）
        narration_path: 解说音频文件路径（可选）
        output_path: 输出文件路径
        volume_config: 音量配置字典，可包含以下键：
            - original: 原声音量（0-1），默认1.0
            - bgm: BGM音量（0-1），默认0.3
            - narration: 解说音量（0-1），默认1.0
        subtitle_enabled: 是否启用字幕，默认True
        subtitle_style: 字幕样式配置字典，可包含以下键：
            - font: 字体名称
            - fontsize: 字体大小
            - color: 字体颜色
            - stroke_color: 描边颜色
            - stroke_width: 描边宽度
            - bg_color: 背景色
            - position: 位置支持 SubtitlePosition 枚举值或 0-1 之间的浮点数（表示距顶部的百分比）
            - method: 文字渲染方法
        font_path: 字体文件路径（.ttf/.otf 等格式）
    """
    # 检查视频文件是否存在
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    # 加载视频
    video = VideoFileClip(video_path)
    subtitle_clips = []

    # 处理字幕（如果启用且提供）- 修复字幕开关bug
    if subtitle_enabled and subtitle_path:
        if os.path.exists(subtitle_path):
            # 检查字体文件
            if font_path and not os.path.exists(font_path):
                logger.warning(f"警告：字体文件不存在: {font_path}")

            try:
                subs = pysrt.open(subtitle_path)
                logger.info(f"读取到 {len(subs)} 条字幕")

                for index, sub in enumerate(subs):
                    start_time = sub.start.ordinal / 1000
                    end_time = sub.end.ordinal / 1000

                    try:
                        # 检查字幕文本是否为空
                        if not sub.text or sub.text.strip() == '':
                            logger.info(f"警告：第 {index + 1} 条字幕内容为空，已跳过")
                            continue

                        # 处理字幕文本：确保是字符串，并处理可能的列表情况
                        if isinstance(sub.text, (list, tuple)):
                            subtitle_text = ' '.join(str(item) for item in sub.text if item is not None)
                        else:
                            subtitle_text = str(sub.text)

                        subtitle_text = subtitle_text.strip()

                        if not subtitle_text:
                            logger.info(f"警告：第 {index + 1} 条字幕处理后为空，已跳过")
                            continue

                        # 创建临时 TextClip 来获取文本高度
                        temp_clip = TextClip(
                            subtitle_text,
                            font=font_path,
                            fontsize=subtitle_style['fontsize'],
                            color=subtitle_style['color']
                        )
                        text_height = temp_clip.h
                        temp_clip.close()

                        # 计算字幕位置
                        position = calculate_subtitle_position(
                            subtitle_style['position'],
                            video.h,
                            text_height
                        )

                        # 创建最终的 TextClip
                        text_clip = (TextClip(
                            subtitle_text,
                            font=font_path,
                            fontsize=subtitle_style['fontsize'],
                            color=subtitle_style['color']
                        )
                            .set_position(position)
                            .set_duration(end_time - start_time)
                            .set_start(start_time))
                        subtitle_clips.append(text_clip)

                    except Exception as e:
                        logger.error(f"警告：创建第 {index + 1} 条字幕时出错: {traceback.format_exc()}")

                logger.info(f"成功创建 {len(subtitle_clips)} 条字幕剪辑")
            except Exception as e:
                logger.info(f"警告：处理字幕文件时出错: {str(e)}")
        else:
            logger.warning(f"字幕文件不存在: {subtitle_path}")
    elif not subtitle_enabled:
        logger.info("字幕已禁用，跳过字幕处理")
    elif not subtitle_path:
        logger.info("未提供字幕文件路径，跳过字幕处理")

    # 合并音频
    audio_clips = []

    # 添加原声（设置音量）
    logger.info(f"音量配置详情: {volume_config}")
    if video.audio is not None:
        original_volume = volume_config['original']
        logger.info(f"应用原声音量: {original_volume}")
        original_audio = video.audio.volumex(original_volume)
        audio_clips.append(original_audio)
        logger.info("原声音频已添加到合成列表")
    else:
        logger.warning("视频没有音轨，无法添加原声")

    # 添加BGM（如果提供）
    if bgm_path:
        logger.info(f"添加背景音乐: {bgm_path}")
        bgm = AudioFileClip(bgm_path)
        if bgm.duration < video.duration:
            bgm = loop_audio_clip(bgm, video.duration)
        else:
            bgm = bgm.subclip(0, video.duration)
        bgm_volume = volume_config['bgm']
        logger.info(f"应用BGM音量: {bgm_volume}")
        bgm = bgm.volumex(bgm_volume)
        audio_clips.append(bgm)

    # 添加解说音频（如果提供）
    if narration_path:
        logger.info(f"添加解说音频: {narration_path}")
        narration_volume = volume_config['narration']
        logger.info(f"应用解说音量: {narration_volume}")
        narration = AudioFileClip(narration_path).volumex(narration_volume)
        audio_clips.append(narration)

    # 合成最终视频（包含字幕）
    if subtitle_clips:
        final_video = CompositeVideoClip([video] + subtitle_clips, size=video.size)
    else:
        logger.info("警告：没有字幕被添加到视频中")
        final_video = video

    if audio_clips:
        logger.info(f"合成音频轨道，共 {len(audio_clips)} 个音频片段")
        final_audio = CompositeAudioClip(audio_clips)
        final_video = final_video.set_audio(final_audio)
        logger.info("音频合成完成")
    else:
        logger.warning("没有音频轨道需要合成")

    # 导出视频 - 使用优化的编码器
    logger.info("开始导出视频...")

    # 获取最优编码器
    from app.utils import ffmpeg_utils
    optimal_encoder = ffmpeg_utils.get_optimal_ffmpeg_encoder()

    # 根据编码器类型设置参数
    ffmpeg_params = []
    if "nvenc" in optimal_encoder:
        ffmpeg_params = ['-preset', 'medium', '-profile:v', 'high']
    elif "videotoolbox" in optimal_encoder:
        ffmpeg_params = ['-profile:v', 'high']
    elif "qsv" in optimal_encoder:
        ffmpeg_params = ['-preset', 'medium']
    elif "vaapi" in optimal_encoder:
        ffmpeg_params = ['-profile', '100']
    elif optimal_encoder == "libx264":
        ffmpeg_params = ['-preset', 'medium', '-crf', '23']

    try:
        final_video.write_videofile(
            output_path,
            codec=optimal_encoder,
            audio_codec='aac',
            fps=video.fps,
            ffmpeg_params=ffmpeg_params
        )
        logger.info(f"视频已导出到: {output_path} (使用编码器: {optimal_encoder})")
    except Exception as e:
        logger.warning(f"使用 {optimal_encoder} 编码器失败: {str(e)}, 尝试软件编码")
        # 降级到软件编码
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=video.fps,
            ffmpeg_params=['-preset', 'medium', '-crf', '23']
        )
        logger.info(f"视频已导出到: {output_path} (使用软件编码)")

    # 清理资源
    video.close()
    for clip in subtitle_clips:
        clip.close()
    if bgm_path:
        bgm.close()
    if narration_path:
        narration.close()


# =============================================================================
# Pipeline-compatible wrapper functions (added to fix missing imports)
# =============================================================================

def create_video_from_segments(
    segments: list,
    output_path: str = "output.mp4",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    config_dict: dict = None,
) -> str:
    """
    Create a video from a list of segments (text, audio, image).

    Args:
        segments: List of dicts, each containing:
            - text: narration text
            - audio_path: path to TTS audio file
            - subtitle_path: path to SRT file (optional)
            - image_path: path to background image (optional)
        output_path: Output video file path.
        width: Video width in pixels.
        height: Video height in pixels.
        fps: Frames per second.
        config_dict: Optional config dict (unused, for API compatibility).

    Returns:
        str: Path to the generated video file.
    """
    from moviepy import ImageClip, AudioFileClip
    from moviepy.video.fx import Loop
    import tempfile, os

    clips = []

    for seg in segments:
        text = seg.get("text", "")
        audio_path = seg.get("audio_path")
        image_path = seg.get("image_path")
        subtitle_path = seg.get("subtitle_path")

        # Determine background clip
        if image_path and os.path.exists(image_path):
            bg_clip = ImageClip(image_path).resize((width, height))
        else:
            # Create a black background if no image
            bg_clip = ImageClip(None).with_duration(5).resize((width, height))

        # Determine duration from audio if available
        duration = 5.0  # default
        audio_clip = None
        if audio_path and os.path.exists(audio_path):
            try:
                audio_clip = AudioFileClip(audio_path)
                duration = audio_clip.duration
                bg_clip = bg_clip.with_duration(duration)
            except Exception as e:
                logger.warning(f"Could not load audio {audio_path}: {e}")

        # Add subtitle text overlay if text provided
        if text:
            try:
                fontsize = int(height * 0.04)
                txt_clip = (
                    TextClip(
                        text=text[:200],  # truncate very long text
                        font_size=fontsize,
                        color="white",
                        stroke_color="black",
                        stroke_width=1.5,
                        font="SimHei",
                        size=(width, None),
                        method="caption",
                    )
                    .with_duration(duration)
                    .with_position("center", "center")
                )
                bg_clip = CompositeVideoClip([bg_clip, txt_clip], size=(width, height))
            except Exception as e:
                logger.warning(f"TextClip creation failed: {e}")

        if audio_clip:
            bg_clip = bg_clip.with_audio(audio_clip)

        clips.append(bg_clip)

    if not clips:
        raise ValueError("No video clips to concatenate")

    if len(clips) == 1:
        final_clip = clips[0]
    else:
        from moviepy import concatenate_videoclips
        final_clip = concatenate_videoclips(clips, method="compose")

    final_clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        threads=2,
        logger=None,
    )

    for c in clips:
        c.close()
    if audio_clip:
        audio_clip.close()

    return output_path


def replace_video_audio_and_subtitle(
    video_path: str,
    audio_path: str,
    subtitle_path: str = None,
    output_path: str = "output_with_audio.mp4",
    font_path: str = None,
    subtitle_style: dict = None,
) -> str:
    """
    Replace/add narration audio and burn-in subtitles to an existing video.

    Args:
        video_path: Path to the original video file.
        audio_path: Path to the narration audio file (MP3/WAV).
        subtitle_path: Optional SRT subtitle file path.
        output_path: Output file path.
        font_path: Path to font file for subtitles (.ttf).
        subtitle_style: Dict with keys: fontsize, color, stroke_color, stroke_width, position.

    Returns:
        str: Path to the output video file.
    """
    from moviepy import VideoFileClip, AudioFileClip
    from moviepy.video.fx import Loop
    import subprocess, os, srt, datetime

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    style = subtitle_style or {}
    fontsize = style.get("fontsize", 50)
    font_color = style.get("color", "white")
    stroke_color = style.get("stroke_color", "black")
    stroke_width = style.get("stroke_width", 2)
    position = style.get("position", "bottom")

    video = VideoFileClip(video_path)
    narration = AudioFileClip(audio_path)

    # If narration is shorter than video, loop it; if longer, trim video
    if narration.duration < video.duration:
        loops_needed = int(video.duration / narration.duration) + 1
        narration = narration.loop(n=loops_needed).with_duration(video.duration)
    else:
        narration = narration.with_duration(video.duration)

    video = video.with_audio(narration)

    # Burn in subtitles if provided
    if subtitle_path and os.path.exists(subtitle_path):
        try:
            with open(subtitle_path, encoding="utf-8") as f:
                subs = list(srt.parse(f.read()))

            font = font_path or "SimHei"
            sub_clips = []
            for sub in subs:
                start_s = sub.start.total_seconds()
                end_s = sub.end.total_seconds()
                dur = max(end_s - start_s, 0.1)
                txt = sub.content.replace("\n", " ")

                try:
                    txt_clip = (
                        TextClip(
                            txt,
                            font_size=fontsize,
                            color=font_color,
                            stroke_color=stroke_color,
                            stroke_width=stroke_width,
                            font=font,
                            size=(video.w, None),
                            method="caption",
                        )
                        .with_duration(dur)
                        .with_start(start_s)
                        .with_position(("center", position))
                    )
                    sub_clips.append(txt_clip)
                except Exception as e:
                    logger.warning(f"Subtitle clip failed: {e}")

            if sub_clips:
                from moviepy import CompositeVideoClip
                video = CompositeVideoClip([video] + sub_clips, size=video.size)
        except Exception as e:
            logger.warning(f"Subtitle burn-in failed: {e}")

    video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        threads=2,
        logger=None,
    )
    video.close()
    narration.close()
    return output_path


def find_silence_boundaries(
    video_path: str,
    min_silence_duration: float = 0.8,
    silence_threshold_db: float = -40.0,
    min_segment_duration: float = 90.0,
    max_segment_duration: float = 300.0,
) -> list:
    """
    通过音频分析找到自然分段点（静音/停顿处）

    Args:
        video_path: 视频路径
        min_silence_duration: 最短静音时长（秒），低于此值不视为分段点
        silence_threshold_db: 静音阈值（dB），低于此值视为静音
        min_segment_duration: 每个片段最短时长（秒）
        max_segment_duration: 每个片段最长时长（秒），超过此值强制分段

    Returns:
        list: [(start, end), ...] 每个片段的起止时间（秒）
    """
    import numpy as np

    try:
        import librosa
    except ImportError:
        logger.warning("[slicer] librosa not installed, using simple amplitude detection")
        return _find_silence_simple(video_path, min_silence_duration, min_segment_duration, max_segment_duration)

    try:
        # Load audio
        y, sr = librosa.load(video_path, sr=None, mono=True)
        duration = len(y) / sr

        # Convert to dB
        db = librosa.util.amplitude_to_db(np.abs(y), ref=np.max)

        # Find silence regions
        is_silence = db < silence_threshold_db

        # Find continuous silence regions
        silence_regions = []
        in_silence = False
        silence_start = 0

        frame_duration = 1.0 / sr
        for i, silence in enumerate(is_silence):
            t = i * frame_duration
            if silence and not in_silence:
                in_silence = True
                silence_start = t
            elif not silence and in_silence:
                in_silence = False
                dur = t - silence_start
                if dur >= min_silence_duration:
                    silence_regions.append((silence_start, t))

        # Build segments from silence points
        if not silence_regions:
            logger.warning("[slicer] No silence regions found, using uniform split")
            return _uniform_segments(duration, min_segment_duration, max_segment_duration)

        segments = []
        seg_start = 0.0

        for silence_start, silence_end in silence_regions:
            seg_end = silence_start  # End at start of silence
            seg_dur = seg_end - seg_start

            if seg_dur >= min_segment_duration:
                segments.append((seg_start, seg_end))
                seg_start = silence_end  # Start after silence ends
            elif seg_dur > 0:
                # Too short, wait for next boundary
                pass

        # Final segment
        if duration - seg_start >= min_segment_duration * 0.5:
            segments.append((seg_start, duration))

        # If we have too few segments, force split at max_segment_duration
        if len(segments) < 2:
            return _uniform_segments(duration, min_segment_duration, max_segment_duration)

        # Merge any segments still exceeding max_segment_duration
        merged = []
        for start, end in segments:
            while end - start > max_segment_duration:
                # Split at midpoint
                mid = start + max_segment_duration / 2
                merged.append((start, mid))
                start = mid
            merged.append((start, end))

        logger.info(f"[slicer] Found {len(merged)} segments from {len(silence_regions)} silence points")
        for i, (s, e) in enumerate(merged):
            logger.info(f"  clip_{i:03d}: {s:.1f}s - {e:.1f}s (dur={e-s:.1f}s)")
        return merged

    except Exception as e:
        logger.exception("[slicer] Error finding silence boundaries")
        return _uniform_segments(300, min_segment_duration, max_segment_duration)


def _find_silence_simple(
    video_path: str,
    min_silence_duration: float,
    min_segment_duration: float,
    max_segment_duration: float,
) -> list:
    """Fallback: use moviepy to detect silence via audio amplitude"""
    from moviepy import AudioClip

    try:
        audio = AudioClip.from_file(video_path)
        duration = audio.duration
        fps = audio.fps or 44100

        # Sample amplitude at low fps
        n_samples = int(duration * 2)  # 2 fps
        times = np.linspace(0, duration, n_samples)

        def get_amplitude(t):
            frame = audio.get_frame(t)
            return np.sqrt(np.mean(frame**2))

        amplitudes = [get_amplitude(t) for t in times]
        threshold = np.mean(amplitudes) * 0.1

        silence_regions = []
        in_silence = False
        silence_start = 0

        for i, (t, amp) in enumerate(zip(times, amplitudes)):
            if amp < threshold and not in_silence:
                in_silence = True
                silence_start = t
            elif amp >= threshold and in_silence:
                in_silence = False
                dur = t - silence_start
                if dur >= min_silence_duration:
                    silence_regions.append((silence_start, t))

        # Build segments
        segments = []
        seg_start = 0.0

        for silence_start, silence_end in silence_regions:
            seg_end = silence_start
            seg_dur = seg_end - seg_start

            if seg_dur >= min_segment_duration:
                segments.append((seg_start, seg_end))
                seg_start = silence_end
            elif seg_dur > 0:
                pass

        if duration - seg_start >= min_segment_duration * 0.5:
            segments.append((seg_start, duration))

        if len(segments) < 2:
            return _uniform_segments(duration, min_segment_duration, max_segment_duration)

        merged = []
        for start, end in segments:
            while end - start > max_segment_duration:
                mid = start + max_segment_duration / 2
                merged.append((start, mid))
                start = mid
            merged.append((start, end))

        return merged

    except Exception:
        duration = 300
        return _uniform_segments(duration, min_segment_duration, max_segment_duration)


def _uniform_segments(duration: float, min_seg: float, max_seg: float) -> list:
    """Fallback: uniform segments"""
    segments = []
    start = 0.0
    while start < duration:
        end = min(start + max_seg, duration)
        if end - start < min_seg * 0.5 and segments:
            # Merge with previous
            prev = segments.pop()
            segments.append((prev[0], end))
        else:
            segments.append((start, end))
        start = end
    return segments


def split_video_into_clips(
    video_path: str,
    output_dir: str,
    max_duration: float = 180.0,
    overlap: float = 3.0,
    min_clip_duration: float = 30.0,
) -> list:
    """
    将长视频智能切割为多个短片段（适合短视频平台）

    Args:
        video_path: 输入视频路径
        output_dir: 输出目录（每个片段单独文件夹）
        max_duration: 每个片段最大时长（秒），默认 180s = 3分钟
        overlap: 片段之间的重叠时长（秒）
        min_clip_duration: 最小片段时长（秒），低于此值会合并到前一个片段

    Returns:
        list: 每个片段的信息 [{clip_path, start, end, duration}, ...]
    """
    from moviepy import VideoFileClip
    import math

    os.makedirs(output_dir, exist_ok=True)
    video = VideoFileClip(video_path)
    total = video.duration

    clips = []
    current = 0.0
    clip_idx = 0

    while current < total:
        clip_end = min(current + max_duration, total)
        clip_out = os.path.join(output_dir, f"clip_{clip_idx:03d}.mp4")

        subclip = video.subclipped(current, clip_end)
        subclip.write_videofile(
            clip_out,
            codec="libx264",
            audio_codec="aac",
            threads=2,
            logger=None,
        )
        subclip.close()

        clips.append({
            "clip_path": clip_out,
            "start": current,
            "end": clip_end,
            "duration": clip_end - current,
        })

        current = clip_end - overlap
        if current < 0:
            current = clip_end
        clip_idx += 1

    video.close()

    # Merge very short clips into previous ones
    merged = []
    skip_next = False
    for i, clip in enumerate(clips):
        if skip_next:
            skip_next = False
            continue
        if clip["duration"] < min_clip_duration and i < len(clips) - 1:
            # Merge with next
            next_clip = clips[i + 1]
            merged[-1]["end"] = next_clip["end"]
            merged[-1]["duration"] = merged[-1]["end"] - merged[-1]["start"]
            # Re-encode merged clip
            from moviepy import VideoFileClip, concatenate_videoclips
            v = VideoFileClip(video_path).subclipped(merged[-1]["start"], merged[-1]["end"])
            v.write_videofile(merged[-1]["clip_path"], codec="libx264", audio_codec="aac", threads=2, logger=None)
            v.close()
            skip_next = True
        else:
            merged.append(clip)

    logger.info(f"[slicer] Split into {len(merged)} clips")
    return merged
