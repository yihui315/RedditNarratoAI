"""
背景视频服务：下载 + 管理背景素材
- 从 YouTube 下载免版权背景视频/音乐（可自选主题）
- 提供多路背景选择（代码/游戏/自然/城市/抽象等）
- 自动裁剪 + 混音合成
"""
import json
import os
import random
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

DEFAULT_BACKGROUND_THEMES = [
    # (name, youtube_url_or_search, credit)
    # 免版权背景视频来源（可替换为自托管URL）
    ("code", "https://www.youtube.com/watch?v=HLJ9U7Xv7vs", "Unsplash/Code"),
    ("nature_forest", "https://www.youtube.com/watch?v=aqz-KE-K7p8", "Pexels/Nature"),
    ("city_night", "https://www.youtube.com/watch?v=JLjdevEH-Hs", "Pexels/City"),
    ("abstract_blue", "https://www.youtube.com/watch?v=2DqS93kQq5I", "Pexels/Abstract"),
    ("minimal_calm", "https://www.youtube.com/watch?v=R_2jRd5G8_0", "Pexels/Minimal"),
    ("gaming_footage", "https://www.youtube.com/watch?v=EwTeatWl0Ms", "Gaming/Footage"),
    ("space_dark", "https://www.youtube.com/watch?v=0jHBD0hB_5s", "Unsplash/Space"),
    ("coastal_waves", "https://www.youtube.com/watch?v=8D6B52X7qV4", "Pexels/Coastal"),
]

BACKGROUND_ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "backgrounds")
VIDEO_DIR = os.path.join(BACKGROUND_ASSET_DIR, "video")
AUDIO_DIR = os.path.join(BACKGROUND_ASSET_DIR, "audio")
METADATA_FILE = os.path.join(BACKGROUND_ASSET_DIR, "metadata.json")


def _load_metadata() -> Dict:
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"video": {}, "audio": {}}


def _save_metadata(meta: Dict) -> None:
    Path(METADATA_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def list_available_backgrounds() -> List[Dict]:
    """返回所有已下载的背景素材列表"""
    meta = _load_metadata()
    result = []
    for name, info in meta.get("video", {}).items():
        if os.path.exists(info.get("path", "")):
            result.append({"type": "video", "name": name, **info})
    for name, info in meta.get("audio", {}).items():
        if os.path.exists(info.get("path", "")):
            result.append({"type": "audio", "name": name, **info})
    return result


def download_background_video(
    name: str,
    youtube_url: str,
    force_redownload: bool = False,
    progress_callback=None,
) -> str:
    """
    下载单个背景视频（YouTube URL）

    Returns:
        视频文件本地路径
    """
    _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)
    Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", name)
    output_path = os.path.join(VIDEO_DIR, f"{safe_name}.mp4")

    if os.path.exists(output_path) and not force_redownload:
        logger.info(f"[bg] Background video already exists: {output_path}")
        return output_path

    _update(f"正在下载背景视频: {name}", 10)
    try:
        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]/best[ext=mp4]",
            "-o", output_path,
            "--no-playlist",
            youtube_url,
        ]
        logger.info(f"[bg] Downloading: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning(f"[bg] yt-dlp failed: {result.stderr[-300:]}")
            # Try with best format
            cmd[1] = "best"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0 and os.path.exists(output_path):
            # Save metadata
            meta = _load_metadata()
            meta["video"][name] = {
                "path": output_path,
                "source": youtube_url,
                "size_mb": os.path.getsize(output_path) / 1024 / 1024,
            }
            _save_metadata(meta)
            _update(f"背景视频下载完成: {name}", 100)
            logger.info(f"[bg] Downloaded: {output_path}")
            return output_path
        else:
            logger.error(f"[bg] Failed to download: {result.stderr[-200:]}")
            return ""

    except Exception as e:
        logger.exception(f"[bg] Error downloading {name}")
        return ""


def download_all_defaults(progress_callback=None) -> None:
    """下载所有默认背景素材（首次运行一次性下载）"""
    _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)
    Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)
    Path(AUDIO_DIR).mkdir(parents=True, exist_ok=True)

    total = len(DEFAULT_BACKGROUND_THEMES)
    for i, (name, url, credit) in enumerate(DEFAULT_BACKGROUND_THEMES):
        pct = int(80 * (i / total))
        _update(f"[{i+1}/{total}] {name}", pct)
        download_background_video(name, url, force_redownload=False)


def get_random_background_video() -> Optional[str]:
    """随机返回一个已下载的背景视频路径"""
    videos = [v["path"] for v in list_available_backgrounds() if v["type"] == "video"]
    return random.choice(videos) if videos else None


def chop_background_video(
    background_video_path: str,
    target_duration: float,
    output_dir: str,
    reddit_id: str = "temp",
) -> Tuple[Optional[str], Optional[str]]:
    """
    从背景视频中截取指定时长的片段

    Returns:
        (video_clip_path, audio_clip_path) 或 (None, None) on failure
    """
    try:
        from moviepy import VideoFileClip, AudioFileClip
    except ImportError:
        logger.warning("[bg] moviepy not available")
        return None, None

    try:
        bg_video = VideoFileClip(background_video_path)
        bg_duration = bg_video.duration

        # 随机选一个起点（确保有足够长度）
        max_start = max(0, bg_duration - target_duration - 1)
        import random
        start_time = random.uniform(0, max_start) if max_start > 0 else 0
        end_time = start_time + target_duration

        # 截取片段
        sub = bg_video.subclipped(start_time, min(end_time, bg_duration))

        out_video = os.path.join(output_dir, f"{reddit_id}_bg.mp4")
        sub.write_videofile(out_video, codec="libx264", audio=False, threads=2, logger=None)
        sub.close()
        bg_video.close()

        # 音频截取
        bg_audio = AudioFileClip(background_video_path).subclipped(start_time, min(end_time, bg_duration))
        out_audio = os.path.join(output_dir, f"{reddit_id}_bg_audio.mp3")
        bg_audio.write_audiofile(out_audio, fps=44100, logger=None)
        bg_audio.close()

        return out_video, out_audio

    except Exception as e:
        logger.exception("[bg] Error chopping background")
        return None, None


def mix_background_audio(
    narration_audio_path: str,
    background_audio_path: str,
    bg_volume: float = 0.25,
    narration_volume: float = 1.0,
    output_path: Optional[str] = None,
) -> str:
    """
    混合解说音频 + 背景音乐

    FFmpeg amix 实现，比 moviepy 更稳定

    Returns:
        混合后的音频文件路径
    """
    if not os.path.exists(narration_audio_path):
        logger.warning("[bg] Narration audio not found, returning background only")
        return background_audio_path or ""

    if not output_path:
        output_path = narration_audio_path.replace(".mp3", "_mixed.mp3")

    bg_vol = str(bg_volume)
    nar_vol = str(narration_volume)

    if background_audio_path and os.path.exists(background_audio_path):
        cmd = [
            "ffmpeg", "-y",
            "-i", narration_audio_path,
            "-i", background_audio_path,
            "-filter_complex",
            f"[1:a]volume={bg_vol}[bg];[0:a]volume={nar_vol}[nar];[nar][bg]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
            "-map", "[aout]",
            "-q:a", "2",
            output_path,
        ]
    else:
        # 只调整解说音量
        cmd = [
            "ffmpeg", "-y",
            "-i", narration_audio_path,
            "-af", f"volume={nar_vol}",
            output_path,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logger.info(f"[bg] Mixed audio saved: {output_path}")
            return output_path
        else:
            logger.warning(f"[bg] Mix failed: {result.stderr[-200:]}")
            return narration_audio_path
    except Exception as e:
        logger.exception("[bg] Error mixing audio")
        return narration_audio_path


def overlay_video_on_background(
    foreground_video_path: str,
    background_video_path: str,
    output_path: str,
    foreground_scale: float = 0.45,
    foreground_x: str = "(main_w-overlay_w)/2",
    foreground_y: str = "(main_h-overlay_h)/2",
    background_volume: float = 0.25,
    narration_volume: float = 1.0,
    progress_callback=None,
) -> str:
    """
    将解说视频叠加到背景视频上（画中画模式）

    FFmpeg filter_complex 实现，比 moviepy 更高效

    参数:
        foreground_video_path: 前景视频（解说视频）
        background_video_path: 背景视频
        output_path: 输出路径
        foreground_scale: 前景缩放比例（0.45 = 占背景45%宽）
        foreground_x/y: 前景位置（居中）
        background_volume: 背景音量（0-1）
        narration_volume: 解说音量（0-1）

    Returns:
        输出文件路径
    """
    _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)

    if not os.path.exists(foreground_video_path):
        raise FileNotFoundError(f"Foreground video not found: {foreground_video_path}")
    if not os.path.exists(background_video_path):
        raise FileNotFoundError(f"Background video not found: {background_video_path}")

    _update("正在合成背景视频...", 10)

    # 获取视频尺寸用于计算缩放
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "json", foreground_video_path],
            capture_output=True, text=True, timeout=30,
        )
        import json
        info = json.loads(probe.stdout)
        fg_w = info["streams"][0]["width"]
        fg_h = info["streams"][0]["height"]
    except Exception:
        fg_w, fg_h = 1920, 1080

    # crop 保证背景和前景比例一致
    crop_w = f"ih*({fg_w/fg_h})"
    crop_h = "ih"

    cmd = [
        "ffmpeg", "-y",
        "-i", foreground_video_path,
        "-i", background_video_path,
        "-filter_complex",
        (
            # 裁剪背景到前景比例
            f"[1:v]crop={crop_w}:{crop_h}[bgCropped];"
            # 缩放背景到标准分辨率
            f"[bgCropped]scale=1920:1080[bgScaled];"
            # 前景缩放
            f"[0:v]scale=iw*{foreground_scale}:-1[fgScaled];"
            # 画中画叠加
            f"[bgScaled][fgScaled]overlay="
            f"x={foreground_x}:y={foreground_y}:"
            f"enable='between(t,0,9999)'[vOut];"
            # 音频混合
            f"[0:a]volume={narration_volume}[narVol];"
            f"[1:a]volume={background_volume}[bgVol];"
            f"[narVol][bgVol]amix=inputs=2:duration=longest[aOut]"
        ),
        "-map", "[vOut]",
        "-map", "[aOut]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    logger.info(f"[bg] overlay cmd: {' '.join(cmd[:20])}...")
    _update("正在渲染背景叠加视频...", 50)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            logger.warning(f"[bg] overlay failed: {result.stderr[-300:]}")
            # Fallback: just return foreground
            import shutil
            shutil.copy2(foreground_video_path, output_path)
            _update("背景叠加失败，使用原始视频", 100)
        else:
            _update("背景叠加完成", 100)
            logger.info(f"[bg] Overlay done: {output_path}")
    except Exception as e:
        logger.exception("[bg] Error in overlay")
        import shutil
        shutil.copy2(foreground_video_path, output_path)

    return output_path


def get_gpu_encoder() -> Tuple[str, str]:
    """
    检测可用的 GPU 编码器

    Returns:
        (video_encoder, audio_encoder) 如 ("h264_nvenc", "aac") 或 ("libx264", "aac")
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        if "h264_nvenc" in result.stdout:
            return "h264_nvenc", "aac"
        if "h264_videotoolbox" in result.stdout:
            return "h264_videotoolbox", "aac"
        if "h264_qsv" in result.stdout:
            return "h264_qsv", "aac"
    except Exception:
        pass
    return "libx264", "aac"


# ── 配置 ─────────────────────────────────────────────────
# 在 config.toml 中配置背景素材：
# [background]
# enable = true
# bg_volume = 0.25       # 背景音量（0-1）
# bg_video = "code"      # 背景视频主题（留空=随机）
# bg_audio_only = false  # 只用背景音乐，不显示背景视频
