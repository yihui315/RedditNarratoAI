"""
B站高清视频下载 — 支持 cookies 续期、1080P+画质
依赖: yt-dlp
"""
import os
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

logger = __import__("app.config_loader", fromlist=["config"]).config.get_logger()


def download_bilibili_video(
    bv_id: str,
    output_dir: str,
    quality: str = "1080",
    cookies_file: str = None,
    progress_callback=None,
) -> dict:
    """
    下载B站视频（支持高清画质）

    Args:
        bv_id: B站 BV 号（如 BV1xx4y1X7z2）
        output_dir: 输出目录
        quality: 画质偏好 "2160"/"1080"/"720"/"480" 或 "best"
        cookies_file: cookies.txt 文件路径（可选，用于解锁高清画质）
        progress_callback: 进度回调 (step, percent)

    Returns:
        dict: {
            "success": bool,
            "video_path": str,      # 视频文件路径
            "audio_path": str,      # 音频文件路径（可能合并在video里）
            "subtitle_path": str,   # 字幕文件路径
            "error": str
        }
    """
    import shutil

    result = {
        "success": False,
        "video_path": "",
        "audio_path": "",
        "subtitle_path": "",
        "error": "",
    }

    try:
        os.makedirs(output_dir, exist_ok=True)
        _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)
        _update("正在解析B站视频...", 10)

        # yt-dlp quality mapping for B站
        # B站 format IDs: 80=4K, 64=1080P高码率, 32=1080P, 16=720P
        quality_map = {
            "2160": "80+71",   # 4K
            "1080": "64+70,32+70",  # 1080P高码率 or 1080P
            "720": "16+64",
            "480": "32+32",
            "best": "bestvideo+bestaudio/best",
        }

        bv_url = f"https://www.bilibili.com/video/{bv_id}"
        output_template = os.path.join(output_dir, f"{bv_id}_%(part)s.%(ext)s")

        # Build yt-dlp args
        ydl_opts = [
            "--no-playlist",
            "--lazy-playlist",
            "--merge-output-format", "mp4",
            "-f", quality_map.get(quality, "bestvideo+bestaudio/best"),
            "-o", output_template,
        ]

        if cookies_file and os.path.exists(cookies_file):
            ydl_opts += ["--cookies", cookies_file]
            _update("使用 cookies 下载（支持高清）...", 15)
        else:
            _update("无 cookies，仅 480P 画质（可选设置 cookies.txt 解锁高清）...", 15)

        # Download subtitle
        ydl_opts += [
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "zh,zh-Hans,zh-CN",
            "--skip-download",
            "--skip-merge",
        ]

        cmd = ["yt-dlp"] + ydl_opts + [bv_url]
        logger.info(f"[B站下载] {' '.join(cmd)}")

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            logger.warning(f"[B站下载] subtitle-only failed: {proc.stderr[:500]}")

        # Now download video + audio
        _update("正在下载视频...", 40)

        ydl_opts_video = [
            "--no-playlist",
            "--merge-output-format", "mp4",
            "-f", quality_map.get(quality, "bestvideo+bestaudio/best"),
            "-o", output_template,
        ]
        if cookies_file and os.path.exists(cookies_file):
            ydl_opts_video += ["--cookies", cookies_file]

        cmd2 = ["yt-dlp"] + ydl_opts_video + [bv_url]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=1800)

        if proc2.returncode != 0:
            result["error"] = f"下载失败: {proc2.stderr[-300:]}"
            return result

        # Find downloaded files
        video_files = sorted(Path(output_dir).glob(f"{bv_id}*.mp4"))
        subtitle_files = sorted(Path(output_dir).glob(f"{bv_id}*.vtt"))

        if not video_files:
            result["error"] = "未找到下载的视频文件"
            return result

        # Rename to final path
        final_video = os.path.join(output_dir, f"{bv_id}_final.mp4")
        shutil.move(str(video_files[0]), final_video)

        result["video_path"] = final_video

        # Convert vtt to srt
        if subtitle_files:
            srt_path = os.path.join(output_dir, f"{bv_id}.srt")
            _vtt_to_srt(subtitle_files[0], srt_path)
            result["subtitle_path"] = srt_path

        # Clean up temp files
        for f in Path(output_dir).glob(f"{bv_id}_part*.mp4"):
            f.unlink(missing_ok=True)

        _update("下载完成", 100)
        result["success"] = True
        logger.info(f"[B站下载] Done: {final_video}")
        return result

    except subprocess.TimeoutExpired:
        result["error"] = "下载超时（B站限速或网络问题）"
    except Exception as e:
        logger.exception("[B站下载] Error")
        result["error"] = str(e)

    return result


def _vtt_to_srt(vtt_path: str, srt_path: str) -> None:
    """Convert WebVTT subtitles to SRT format"""
    try:
        content = open(vtt_path, encoding="utf-8").read()
        # Remove WEBVTT header and tags
        lines = content.split("\n")
        srt_lines = []
        counter = 0
        timestamp = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT"):
                continue
            # Timestamps: 00:00:00.000 --> 00:00:01.000
            if "-->" in line:
                timestamp = line.replace(".", ",")
                counter += 1
                srt_lines.append(f"{counter}\n{timestamp}")
            elif line and not line.startswith("NOTE"):
                srt_lines.append(line)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))
    except Exception as e:
        logger.warning(f"字幕转换失败: {e}")


def download_with_cookies_flow(
    bv_id: str,
    output_dir: str,
    cookies_text: str = None,
    quality: str = "1080",
    progress_callback=None,
) -> dict:
    """
    使用内联 cookies 文本下载（优先级高于文件）
    cookies_text: 浏览器开发者工具复制的 cookies 字符串
    """
    cookies_file = None
    if cookies_text:
        import tempfile
        fd, cookies_file = tempfile.mkstemp(suffix=".txt")
        os.write(fd, cookies_text.encode("utf-8"))
        os.close(fd)

    try:
        return download_bilibili_video(
            bv_id=bv_id,
            output_dir=output_dir,
            quality=quality,
            cookies_file=cookies_file,
            progress_callback=progress_callback,
        )
    finally:
        if cookies_file:
            os.unlink(cookies_file)
