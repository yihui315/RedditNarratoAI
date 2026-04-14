"""
src/chapter_draft.py - 章节草稿生成
─────────────────────────────────────
输入: transcript.json + scenes.json
输出: work_dir/chapter_draft.json

模型: qw3.6 (Ollama)
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_ollama, call_structured


SYSTEM_PROMPT = """你是一个专业的电影解说结构分析师。
根据电影的语音转写和镜头切分信息，将电影划分为3个解说章节。
严格输出JSON格式，不要有任何额外文字。"""


USER_TEMPLATE = """请分析以下电影转写和镜头信息，生成3章解说结构：

电影总时长: {duration} 秒
镜头数量: {num_scenes} 个

转写内容:
{transcript_text}

镜头切分:
{scenes_text}

要求:
1. 将电影合理划分为3个章节（开头/中段/结尾）
2. 每章需要: id, start_scene, end_scene, summary, characters, key_events
3. summary 要能概括该章节的核心内容
4. characters 列出出场人物
5. key_events 列出3-5个关键事件
6. 输出必须是合法的JSON对象"""



def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口: 读取 transcript + scenes → qw3.6 → chapter_draft.json"""
    output_path = work_dir / "chapter_draft.json"

    if output_path.exists():
        print(f"  chapter_draft.json 已存在，跳过")
        return

    # ── 加载输入 ──────────────────────────────────────────────────────────
    transcript = json.loads((work_dir / "transcript.json").read_text(encoding="utf-8"))
    scenes      = json.loads((work_dir / "scenes.json").read_text(encoding="utf-8"))

    # 估算总时长
    last_seg = transcript["transcript"][-1] if transcript["transcript"] else {"end": "00:00:00.000"}
    duration = _srt_to_sec(last_seg["end"])

    # 拼接受入文本
    transcript_text = "\n".join(
        f"[{t['start']}→{t['end']}] {t['text']}"
        for t in transcript["transcript"]
    )
    scenes_text = "\n".join(
        f"镜头{s['scene_id']}: {s['start']} → {s['end']}"
        for s in scenes["scenes"]
    )

    user_prompt = USER_TEMPLATE.format(
        duration=duration,
        num_scenes=len(scenes["scenes"]),
        transcript_text=transcript_text or "（无转写内容）",
        scenes_text=scenes_text,
    )

    print(f"  调用 qw3.6 生成章节草稿...")
    result = call_structured("qw3.6", user_prompt, SYSTEM_PROMPT)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 章节草稿完成: {len(result.get('chapters', []))} 章 → {output_path}")


def _srt_to_sec(t: str) -> float:
    """SRT时间 "HH:MM:SS.mmm" → 秒"""
    parts = t.replace(".", ":").split(":")
    h, m, s, ms = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    return h * 3600 + m * 60 + s + ms / 1000
