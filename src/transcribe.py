"""
src/transcribe.py - WhisperX 语音转写
─────────────────────────────────────
输入: movie_path (MP4/AVI/MKV)
输出: work_dir/transcript.json
      时间戳格式: "HH:MM:SS.mmm"
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict
import datetime


def _sec_to_srt_time(sec: float) -> str:
    """秒 → SRT时间格式 HH:MM:SS.mmm"""
    td = datetime.timedelta(seconds=sec)
    h = td.seconds // 3600
    m = (td.seconds % 3600) // 60
    s = td.seconds % 60
    ms = td.microseconds // 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _run_whisperx(audio_path: str, model: str = "base") -> Dict:
    """调用 faster-whisper 转写"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed: pip install faster-whisper")

    device = "cpu"
    compute_type = "int8"
    try:
        model_instance = WhisperModel(model, device=device, compute_type=compute_type)
    except Exception:
        # fallback to default
        model_instance = WhisperModel(model)

    segments, _ = model_instance.transcribe(audio_path, language="zh", beam_size=5)

    result = []
    for seg in segments:
        result.append({
            "start": _sec_to_srt_time(seg.start),
            "end":   _sec_to_srt_time(seg.end),
            "text":  seg.text.strip(),
        })
    return {"transcript": result}


def _extract_audio(video_path: str, audio_path: str) -> None:
    """用 FFmpeg 提取音频"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr[-300:]}")


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """
    主入口: 提取音频 → WhisperX转写 → 保存 transcript.json
    """
    movie_path = context["movie_path"]
    output_path = work_dir / "transcript.json"

    # 已完成检查由 task_manager 处理
    if output_path.exists():
        print(f"  transcript.json 已存在，跳过")
        return

    print(f"  电影: {movie_path}")

    # ── Step 1: 提取音频 ────────────────────────────────────────────────
    audio_path = work_dir / "audio.wav"
    print(f"  提取音频 → {audio_path}")
    _extract_audio(movie_path, str(audio_path))

    # ── Step 2: WhisperX 转写 ───────────────────────────────────────────
    print(f"  运行 WhisperX 转写...")
    result = _run_whisperx(str(audio_path))
    num_sentences = len(result.get("transcript", []))
    print(f"  转写完成: {num_sentences} 句")

    # ── Step 3: 保存 ─────────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 保存至: {output_path}")
