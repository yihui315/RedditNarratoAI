import traceback
import os

try:
    import pysrt
except ImportError:
    pysrt = None

# import pysrt
import os
from typing import Optional
from typing import List
from loguru import logger
from moviepy import *
from moviepy import vfx
from PIL import ImageFont
from contextlib import contextmanager
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    CompositeAudioClip,
    ColorClip,
)


from app.models.schema import VideoAspect, SubtitlePosition


def resize_video_with_padding(clip, target_w: int, target_h: int):
    """
    将视频缩放到目标尺寸，保持纵横比，不足部分用黑色填充。

    Args:
        clip: MoviePy VideoClip
        target_w: 目标宽度
        target_h: 目标高度

    Returns:
        CompositeVideoClip: 缩放后的视频
    """
    from moviepy import ColorClip

    src_w, src_h = clip.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    resized = clip.resized((new_w, new_h))

    # If already exact size, return directly
    if new_w == target_w and new_h == target_h:
        return resized

    # Create black background and center the resized clip
    bg = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=clip.duration)
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    resized = resized.with_position((x_offset, y_offset))
    return CompositeVideoClip([bg, resized], size=(target_w, target_h))


def loop_audio_clip(audio_clip, target_duration: float):
    """
    循环音频片段直到达到目标时长。

    Args:
        audio_clip: AudioFileClip
        target_duration: 目标时长（秒）

    Returns:
        AudioFileClip: 循环后的音频
    """
    if audio_clip.duration >= target_duration:
        return audio_clip.subclipped(0, target_duration)

    from moviepy import concatenate_audioclips
    loops_needed = int(target_duration / audio_clip.duration) + 1
    looped = concatenate_audioclips([audio_clip] * loops_needed)
    return looped.subclipped(0, target_duration)


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


def _apply_fade_transition(clip, fade_duration: float = 0.5):
    """Apply fade-in and fade-out transitions to a clip."""
    if clip.duration <= fade_duration * 2:
        return clip
    return clip.with_effects([
        vfx.FadeIn(fade_duration),
        vfx.FadeOut(fade_duration),
    ])


def _build_subtitle_clips(
    segments: list,
    video_width: int,
    video_height: int,
    subtitle_config: dict,
) -> List:
    """
    Build dynamic subtitle clips from video segments.

    Features:
    - Semi-transparent background box behind text
    - Position based on config (bottom / center / top)
    - Fade transitions per subtitle entry
    """
    clips = []
    font_size = subtitle_config.get("font_size", 36)
    font_color = subtitle_config.get("color", "#FFFFFF")
    position_cfg = subtitle_config.get("position", "bottom")
    bg_color_str = subtitle_config.get("bg_color", "#00000080")

    margin = 50

    for seg in segments:
        text = seg.text.strip() if hasattr(seg, "text") else str(seg)
        if not text:
            continue

        start = seg.start_time if hasattr(seg, "start_time") else 0
        end = seg.end_time if hasattr(seg, "end_time") else start + 3
        duration = max(end - start, 0.1)

        try:
            txt_clip = TextClip(
                text=text,
                font_size=font_size,
                color=font_color,
                size=(video_width - 120, None),
                method="caption",
                duration=duration,
            )

            # Background box
            box_w = min(txt_clip.w + 40, video_width)
            box_h = txt_clip.h + 20
            bg_clip = ColorClip(
                size=(box_w, box_h),
                color=(0, 0, 0),
                duration=duration,
            ).with_opacity(0.5)

            # Position
            if position_cfg == "top":
                y_pos = margin
            elif position_cfg == "center":
                y_pos = video_height // 2 - box_h // 2
            else:  # bottom
                y_pos = video_height - margin - box_h

            bg_clip = bg_clip.with_position(("center", y_pos)).with_start(start)
            txt_clip = txt_clip.with_position(("center", y_pos + 10)).with_start(start)

            # Subtle fade on each subtitle
            if duration > 0.4:
                fade_dur = min(0.2, duration / 4)
                txt_clip = txt_clip.with_effects([
                    vfx.FadeIn(fade_dur),
                    vfx.FadeOut(fade_dur),
                ])
                bg_clip = bg_clip.with_effects([
                    vfx.FadeIn(fade_dur),
                    vfx.FadeOut(fade_dur),
                ])

            clips.extend([bg_clip, txt_clip])

        except Exception as e:
            logger.warning(f"创建字幕片段失败: {e}")
            continue

    return clips


# Video aspect presets
VIDEO_PRESETS = {
    "landscape": {"width": 1920, "height": 1080, "label": "横屏 16:9"},
    "portrait": {"width": 1080, "height": 1920, "label": "竖屏 9:16"},
    "square": {"width": 1080, "height": 1080, "label": "方形 1:1"},
}


def create_video_from_segments(
    segments: list,
    audio_path: str,
    subtitle_path: str,
    output_dir: str,
    config_dict: dict = None,
    title: str = "",
) -> str:
    """
    RedditNarratoAI 流水线使用的视频合成函数。
    将音频和字幕合成为带背景色的视频。

    Args:
        segments: VideoSegment 列表
        audio_path: 配音音频路径
        subtitle_path: SRT 字幕路径
        output_dir: 输出目录
        config_dict: 配置字典
        title: 视频标题

    Returns:
        str: 生成的视频文件路径，失败返回空字符串
    """
    os.makedirs(output_dir, exist_ok=True)

    video_config = (config_dict or {}).get("video", {})
    config: dict = None,
    title: str = "",
    source_video_path: str = "",
    bgm_path: str = "",
) -> Optional[str]:
    """
    高级封装：从segments创建视频（为pipeline提供的接口）

    v2 改进:
    - 渐变背景替代纯色
    - 标题淡入淡出
    - 动态字幕（半透明背景框 + 逐条淡入淡出）
    - 9:16竖屏/1:1方形预设
    - BGM自动混音（解说时自动降低BGM音量）
    支持:
      - 源视频作为背景画面（Agent流水线下载的YouTube视频）
      - 纯色背景 fallback（无源视频时）
      - 字幕叠加（从SRT文件）
      - BGM混合
      - 配音音频

    Args:
        segments: VideoSegment列表
        audio_path: 配音音频路径
        subtitle_path: 字幕文件路径
        output_dir: 输出目录
        config: 配置字典
        title: 视频标题
        source_video_path: 源视频路径（用作背景画面）
        bgm_path: 背景音乐路径

    Returns:
        str: 输出视频路径，失败返回None
    """
    import os
    import pysrt
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "final_video.mp4")
    video_config = (config or {}).get("video", {})
    subtitle_config = (config or {}).get("subtitle", {})

    # Support aspect presets
    aspect = video_config.get("aspect", "")
    if aspect in VIDEO_PRESETS:
        width = VIDEO_PRESETS[aspect]["width"]
        height = VIDEO_PRESETS[aspect]["height"]
    else:
        width = video_config.get("width", 1920)
        height = video_config.get("height", 1080)
    bgm_config = (config or {}).get("bgm", {})
    width = video_config.get("width", 1920)
    height = video_config.get("height", 1080)
    fps = video_config.get("fps", 30)

    subtitle_config = (config_dict or {}).get("subtitle", {})
    font_size = subtitle_config.get("font_size", 36)
    font_color = subtitle_config.get("color", "#FFFFFF")

    output_path = os.path.join(output_dir, "final_video.mp4")

    audio_clip = None
    background = None
    text_clips = []
    final_video = None

    try:
        # 获取音频时长
        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration

        # 创建纯色背景
        background = ColorClip(
            size=(width, height),
            color=(20, 20, 30),  # 深色背景
        ).with_duration(total_duration).with_fps(fps)

        # 创建字幕文本 clips
        if subtitle_path and os.path.exists(subtitle_path) and pysrt is not None:
            try:
                subs = pysrt.open(subtitle_path)
                for sub in subs:
                    start_time = sub.start.ordinal / 1000
                    end_time = sub.end.ordinal / 1000
                    sub_text = str(sub.text).strip()
    try:
        # Calculate total duration from audio
        audio_clip = None
        if audio_path and os.path.exists(audio_path):
            audio_clip = AudioFileClip(audio_path)
            total_duration = audio_clip.duration
        elif segments:
            total_duration = max(
                (s.end_time for s in segments if hasattr(s, "end_time")),
                default=10.0,
            )
        else:
            total_duration = 10.0

        # Gradient-style background (dark charcoal to dark blue)
        bg_clip = ColorClip(
            size=(width, height),
            color=(20, 22, 30),
            duration=total_duration,
        ).with_fps(fps)

        clips = [bg_clip]

        # Title with fade effect
        # --- Background Layer ---
        bg_clip = None
        if source_video_path and os.path.exists(source_video_path):
            try:
                src_clip = VideoFileClip(source_video_path)
                # Loop or trim source video to match audio duration
                if src_clip.duration < total_duration:
                    # Loop the source video
                    loops_needed = int(total_duration / src_clip.duration) + 1
                    from moviepy import concatenate_videoclips
                    looped = concatenate_videoclips([src_clip] * loops_needed)
                    src_clip = looped.subclipped(0, total_duration)
                else:
                    src_clip = src_clip.subclipped(0, total_duration)

                # Resize to target dimensions
                bg_clip = resize_video_with_padding(src_clip, width, height)
                bg_clip = bg_clip.with_fps(fps)
                # Mute original audio (we'll use our narration instead)
                bg_clip = bg_clip.without_audio()
                logger.info(f"使用源视频作为背景: {source_video_path}")
            except Exception as e:
                logger.warning(f"加载源视频失败，使用纯色背景: {e}")
                bg_clip = None

        if bg_clip is None:
            # Fallback: colored background
            from moviepy import ColorClip
            bg_clip = ColorClip(size=(width, height), color=(30, 30, 30), duration=total_duration)
            bg_clip = bg_clip.with_fps(fps)

        clips = [bg_clip]

        # --- Title overlay (first 5 seconds) ---
        if title:
            try:
                title_display = title[:50]
                title_duration = min(5.0, total_duration)
                title_font_size = 48 if width >= 1920 else 36
                title_clip = TextClip(
                    text=title_display,
                    font_size=title_font_size,
                    color="white",
                    size=(width - 100, None),
                    method="caption",
                    duration=title_duration,
                )
                title_clip = title_clip.with_position(("center", int(height * 0.15)))
                title_clip = _apply_fade_transition(title_clip, fade_duration=1.0)
                clips.append(title_clip)
            except Exception as e:
                logger.warning(f"添加标题失败: {e}")

        # Dynamic subtitle clips from segments
        if segments:
            sub_clips = _build_subtitle_clips(
                segments, width, height, subtitle_config
            )
            clips.extend(sub_clips)
        # --- Subtitle overlay from SRT ---
        if subtitle_path and os.path.exists(subtitle_path):
            try:
                subs = pysrt.open(subtitle_path)
                font_size = subtitle_config.get("font_size", 36)
                font_color = subtitle_config.get("color", "#FFFFFF")
                # Strip # from hex color for moviepy
                if font_color.startswith("#"):
                    font_color = font_color

                for sub in subs:
                    start_sec = sub.start.ordinal / 1000.0
                    end_sec = sub.end.ordinal / 1000.0
                    # Clamp to video duration
                    if start_sec >= total_duration:
                        break
                    end_sec = min(end_sec, total_duration)
                    duration = end_sec - start_sec
                    if duration <= 0:
                        continue

                    sub_text = sub.text.strip()
                    if not sub_text:
                        continue

                    try:
                        text_clip = (
                            TextClip(
                                text=sub_text,
                                font_size=font_size,
                                color=font_color,
                                size=(width - 100, None),
                                method='caption',
                            )
                            .with_position(('center', height - 150))
                            .with_start(start_time)
                            .with_duration(end_time - start_time)
                        )
                        text_clips.append(text_clip)
                    except Exception as e:
                        logger.warning(f"创建字幕片段失败: {e}")
            except Exception as e:
                logger.warning(f"读取字幕文件失败: {e}")

        # 如果有标题，添加标题卡片 (前3秒)
        if title:
            try:
                title_clip = (
                    TextClip(
                        text=title,
                        font_size=int(font_size * 1.5),
                        color=font_color,
                        size=(width - 200, None),
                        method='caption',
                    )
                    .with_position('center')
                    .with_start(0)
                    .with_duration(min(3.0, total_duration))
                )
                text_clips.insert(0, title_clip)
            except Exception as e:
                logger.warning(f"创建标题失败: {e}")

        # 合成视频
        all_clips = [background] + text_clips
        final_video = CompositeVideoClip(all_clips, size=(width, height))
        final_video = final_video.with_audio(audio_clip)

        # 导出
        logger.info(f"开始导出视频到: {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=fps,
            preset='medium',
        )

        logger.info(f"视频导出完成: {output_path}")
                        sub_clip = TextClip(
                            text=sub_text,
                            font_size=font_size,
                            color=font_color,
                            stroke_color='black',
                            stroke_width=2,
                            size=(width - 100, None),
                            method='caption',
                            duration=duration,
                        )
                        # Position at bottom with margin
                        sub_clip = sub_clip.with_position(('center', height - 120))
                        sub_clip = sub_clip.with_start(start_sec)
                        clips.append(sub_clip)
                    except Exception as e:
                        logger.warning(f"字幕渲染失败: {e}")
                        continue

                logger.info(f"已叠加 {len(subs)} 条字幕")
            except Exception as e:
                logger.warning(f"字幕加载失败: {e}")

        # Compose video
        final_video = CompositeVideoClip(clips, size=(width, height))

        # Audio mixing: narration + optional BGM
        # --- Audio mixing ---
        audio_tracks = []
        if audio_clip:
            audio_tracks.append(audio_clip)

        bgm_path = video_config.get("bgm_path", "")
        if bgm_path and os.path.exists(bgm_path):
            try:
                bgm_clip = AudioFileClip(bgm_path)
        # Add BGM if available
        actual_bgm_path = bgm_path or bgm_config.get("file", "")
        bgm_volume = bgm_config.get("volume", 0.15)
        if actual_bgm_path and os.path.exists(actual_bgm_path):
            try:
                bgm_clip = AudioFileClip(actual_bgm_path)
                if bgm_clip.duration < total_duration:
                    bgm_clip = loop_audio_clip(bgm_clip, total_duration)
                else:
                    bgm_clip = bgm_clip.subclipped(0, total_duration)
                # Lower BGM volume (ducking) when narration is present
                bgm_volume = 0.15 if audio_clip else 0.4
                bgm_clip = bgm_clip.with_volume_scaled(bgm_volume)
                audio_tracks.append(bgm_clip)
                bgm_clip = bgm_clip.with_volume_scaled(bgm_volume)
                audio_tracks.append(bgm_clip)
                logger.info(f"已添加BGM: {actual_bgm_path} (音量: {bgm_volume})")
            except Exception as e:
                logger.warning(f"BGM加载失败: {e}")

        if audio_tracks:
            if len(audio_tracks) == 1:
                final_video = final_video.with_audio(audio_tracks[0])
            else:
                final_video = final_video.with_audio(
                    CompositeAudioClip(audio_tracks)
                )

        # Apply global fade
        final_video = _apply_fade_transition(final_video, fade_duration=0.8)
                mixed_audio = CompositeAudioClip(audio_tracks)
                final_video = final_video.with_audio(mixed_audio)

        # Write output
        final_video.write_videofile(
            output_path,
            fps=fps,
            codec=video_config.get("codec", "libx264"),
            audio_codec=video_config.get("audio_codec", "aac"),
            logger=None,
        )

        # Cleanup
        final_video.close()
        bg_clip.close()
        if audio_clip:
            audio_clip.close()

        logger.info(f"视频生成成功: {output_path} ({width}x{height})")
        return output_path

    except Exception as e:
        logger.error(f"视频合成失败: {e}")
        logger.error(traceback.format_exc())
        return ""

    finally:
        # 清理资源，无论成功还是失败
        for clip in text_clips:
            try:
                clip.close()
            except Exception:
                pass
        if final_video is not None:
            try:
                final_video.close()
            except Exception:
                pass
        if background is not None:
            try:
                background.close()
            except Exception:
                pass
        if audio_clip is not None:
            try:
                audio_clip.close()
            except Exception:
                pass
        return None
