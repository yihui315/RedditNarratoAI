"""
src/render_manifest.py - 渲染清单生成
──────────────────────────────────────
输入: scenes.json + final_scripts/ + scene_prompts/
输出: work_dir/render_manifest.json

根据镜头切分和旁白时长，将每段视频切分为合理长度的clips
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_minimax


def _sec_to_time(sec: float) -> str:
    """秒 → "HH:MM:SS" """
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _time_to_sec(t: str) -> float:
    """"HH:MM:SS" 或 "HH:MM:SS.mmm" → 秒"""
    parts = t.replace(".", ":").split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    output_path = work_dir / "render_manifest.json"

    if output_path.exists():
        print(f"  render_manifest.json 已存在，跳过")
        return

    # ── 收集各段信息 ────────────────────────────────────────────────────
    final_dir   = work_dir / "final_scripts"
    prompts_dir = work_dir / "scene_prompts"
    scenes_data = json.loads((work_dir / "scenes.json").read_text(encoding="utf-8"))
    scenes = scenes_data["scenes"]

    manifest = {"clips": [], "ffmpeg_commands": []}

    for part_name in ["part1", "part2", "part3"]:
        script_path  = final_dir / f"final_{part_name}.json"
        if not script_path.exists():
            continue

        script = json.loads(script_path.read_text(encoding="utf-8"))
        sentences = script.get("sentences", [])
        if not sentences:
            continue

        # 计算总音频时长
        total_duration = sum(s.get("duration", 4) for s in sentences)

        # 将时长映射到镜头
        clips = _distribute_to_scenes(sentences, scenes, total_duration)

        part_num = part_name.replace("part", "")
        manifest["clips"].extend([
            {
                "scene_id": c["scene_id"],
                "start": c["start"],
                "end": c["end"],
            }
            for c in clips
        ])

        # 生成 FFmpeg 合成命令
        clip_files = [f"clip_{part_num}_{i+1}.mp4" for i in range(len(clips))]
        concat_file = work_dir / "concat" / f"list_{part_num}.txt"
        concat_file.parent.mkdir(exist_ok=True)
        concat_file.write_text(
            "\n".join(f"file '{f}'" for f in clip_files),
            encoding="utf-8"
        )

        manifest["ffmpeg_commands"].append({
            "part": part_num,
            "audio": f"audio/audio_{part_name}.mp3",
            "subtitle": f"subtitles/subtitle_{part_name}.srt",
            "clips": clip_files,
            "concat_list": str(concat_file),
        })

    # 全局设置
    manifest["global"] = {
        "encoder": "libx264",
        "resolution": "1920x1080",
        "fps": 30,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 渲染清单生成: {len(manifest['clips'])} clips → {output_path}")


def _distribute_to_scenes(sentences: list, scenes: list, total_duration: float):
    """
    将句子分配到镜头
    策略: 按比例分配，每句时长 → 最近镜头
    """
    if not scenes:
        # 无镜头信息，按平均时长切分
        avg_len = total_duration / max(len(sentences), 1)
        return [{"scene_id": 1, "start": "00:00:00", "end": _sec_to_time(avg_len)}]

    clip_duration = total_duration / len(scenes)
    clips = []

    for i, scene in enumerate(scenes):
        # 计算该镜头覆盖的时间范围
        t_start = i * clip_duration
        t_end   = (i + 1) * clip_duration

        # 找覆盖这个时间范围的句子
        scene_start_sec = _time_to_sec(scene["start"])
        scene_end_sec   = _time_to_sec(scene["end"])

        clips.append({
            "scene_id": scene["scene_id"],
            "start": scene["start"],
            "end":   scene["end"],
        })

    return clips
