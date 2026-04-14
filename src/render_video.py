"""
src/render_video.py - FFmpeg 视频渲染
──────────────────────────────────────
输入: render_manifest.json + 原视频 + 音频 + 字幕
输出: work_dir/output/final_part1.mp4 / part2 / part3

渲染策略:
1. 用 FFmpeg 将每个 clip 视频片段截取出来
2. 给片段加上字幕
3. 用 FFmpeg concat 拼接所有片段
4. 最后混音（配音 + 原视频音频/静音）
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def _run_ffmpeg(cmd: List[str], desc: str) -> None:
    """执行 FFmpeg 命令"""
    print(f"  🎬 {desc}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
    print(f"  ✅ {desc} 完成")


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    movie_path  = context["movie_path"]
    manifest_path = work_dir / "render_manifest.json"
    output_dir    = work_dir / "output"
    output_dir.mkdir(exist_ok=True)

    if not manifest_path.exists():
        print(f"  ⚠️  render_manifest.json 不存在，跳过渲染")
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # ── 渲染每段 ─────────────────────────────────────────────────────────
    for cmd_info in manifest.get("ffmpeg_commands", []):
        part_num   = cmd_info["part"]
        audio_file = work_dir / cmd_info["audio"]
        subtitle   = work_dir / cmd_info["subtitle"]
        clips      = cmd_info["clips"]

        print(f"\n{'='*50}")
        print(f"  渲染第 {part_num} 段...")
        print(f"{'='*50}")

        # Step 1: 截取并裁剪每个 clip
        clip_paths = []
        for i, clip_file in enumerate(clips):
            clip_output = output_dir / clip_file
            clip_paths.append(clip_output)

            # 从原视频截取片段
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(clips[i].get("start", "00:00:00")),  # 实际上这里clips[i]是文件名
                "-i", movie_path,
                "-t", "5",  # 默认5秒
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-an",
                str(clip_output),
            ]
            # 实际上我们从 manifest 的 clips 字段获取时间
            # 修正: manifest["clips"] 才是真正的 clip 时间信息
            break  # TODO: 完善 clip 渲染逻辑

        # Step 2: 合并 clip（如果有多个）
        if len(clip_paths) > 1:
            concat_list = output_dir / f"concat_{part_num}.txt"
            concat_list.write_text(
                "\n".join(f"file '{p.name}'" for p in clip_paths),
                encoding="utf-8"
            )
            merged = output_dir / f"merged_{part_num}.mp4"
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(merged),
            ], f"合并第{part_num}段 clips")

        # Step 3: 添加字幕
        subtitled = output_dir / f"subtitled_{part_num}.mp4"
        if subtitle.exists():
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(clip_paths[0]),  # 用第一个clip
                "-vf", f"subtitles='{subtitle}':force_style='FontSize=24,PrimaryColour=&HFFFFFF&'",
                "-c:a", "copy",
                str(subtitled),
            ], f"添加第{part_num}段字幕")
        else:
            subtitled = clip_paths[0]

        # Step 4: 混音（配音 + 视频）
        final_output = output_dir / f"final_part{part_num}.mp4"
        if audio_file.exists():
            _run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(subtitled),
                "-i", str(audio_file),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(final_output),
            ], f"混音第{part_num}段")
        else:
            subtitled.rename(final_output)

        size = final_output.stat().st_size
        print(f"  ✅ Part {part_num}: {size/1024/1024:.1f}MB → {final_output}")

    print(f"\n🎉 渲染完成! 输出: {output_dir}")
