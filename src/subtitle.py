"""
src/subtitle.py - SRT 字幕生成
──────────────────────────────
输入: final_scripts/final_{part}.json
输出: work_dir/subtitles/subtitle_{part}.srt

时间轴基于 estimated_duration 累加计算
SRT格式: 1\nHH:MM:SS,mmm --> HH:MM:SS,mmm\ntext\n\n
"""

import json
from pathlib import Path
from typing import Any, Dict
import datetime


def _sec_to_srt_time(sec: float) -> str:
    """秒 → SRT时间格式 HH:MM:SS,mmm"""
    td = datetime.timedelta(seconds=sec)
    h = td.seconds // 3600
    m = (td.seconds % 3600) // 60
    s = td.seconds % 60
    ms = td.microseconds // 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _generate_srt(sentences: list, start_offset: float = 0.0) -> str:
    """根据句子列表和时长估算生成SRT"""
    blocks = []
    current_time = start_offset

    for i, sent in enumerate(sentences, start=1):
        text = sent["text"]
        duration = sent.get("duration", sent.get("estimated_duration_sec", 4.0))

        start_sec = current_time
        end_sec   = current_time + duration

        start_srt = _sec_to_srt_time(start_sec)
        end_srt   = _sec_to_srt_time(end_sec)

        blocks.append(f"{i}\n{start_srt} --> {end_srt}\n{text}\n")
        current_time = end_sec

    return "\n".join(blocks)


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    final_dir    = work_dir / "final_scripts"
    subtitle_dir = work_dir / "subtitles"
    subtitle_dir.mkdir(exist_ok=True)

    for part_name in ["part1", "part2", "part3"]:
        script_path  = final_dir / f"final_{part_name}.json"
        subtitle_path = subtitle_dir / f"subtitle_{part_name}.srt"

        if subtitle_path.exists():
            print(f"  subtitle_{part_name}.srt 已存在，跳过")
            continue

        if not script_path.exists():
            print(f"  ⚠️  {script_path} 不存在，跳过")
            continue

        script = json.loads(script_path.read_text(encoding="utf-8"))
        sentences = script.get("sentences", [])

        if not sentences:
            print(f"  ⚠️  {part_name} 无句子，跳过")
            continue

        srt_content = _generate_srt(sentences)
        subtitle_path.write_text(srt_content, encoding="utf-8")

        print(f"  ✅ {part_name}: {len(sentences)} 句 → {subtitle_path}")
