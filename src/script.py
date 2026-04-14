"""
src/script.py - 解说脚本生成（MiniMax）
────────────────────────────────────────
输入: outline.json
输出: work_dir/scripts/script_part1.json
      work_dir/scripts/script_part2.json
      work_dir/scripts/script_part3.json

模型: MiniMax API
每段生成一段完整解说（开头钩子→中段→结尾悬念）
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个电影解说金牌编剧。
根据三段式大纲，为指定段落生成完整的解说脚本。
严格输出JSON，不要有任何额外文字。

脚本格式:
{
  "paragraph_text": "整段解说的完整连贯文本（用于TTS配音）",
  "sentences": [
    {"id": 1, "text": "单句内容", "estimated_duration_sec": 4}
  ]
}
注意: sentences 里的每句是从 paragraph_text 拆分出来的，
estimated_duration_sec 是该句预计朗读时长（秒）。"""


PART_PROMPTS = {
    "part1": """请为第一段（开头）生成解说脚本：

主题: {theme}
开头钩子: {hook}
关键要点: {key_points}
结尾悬念: {ending_hook}

要求:
1. 开头前3句必须有强烈冲击力，立刻抓住观众
2. 整体要有节奏：短句快节奏 + 长句渲染情绪
3. 每句 estimated_duration_sec 控制在 3-6 秒
4. paragraph_text 要通顺流畅，适合直接配音
5. 必须包含开头钩子和结尾悬念（引导看下一段）
6. 总时长控制在 60-90 秒的解说长度""",

    "part2": """请为第二段（中段）生成解说脚本：

主题: {theme}
开头钩子: {hook}
关键要点: {key_points}
结尾悬念: {ending_hook}

要求:
1. 承接第一段的悬念，层层递进
2. 要有反转和情绪波动，不能平铺直叙
3. 每句 estimated_duration_sec 控制在 3-6 秒
4. paragraph_text 要通顺流畅，适合直接配音
5. 结尾留有悬念，引导观众继续看第三段
6. 总时长控制在 60-90 秒的解说长度""",

    "part3": """请为第三段（结尾）生成解说脚本：

主题: {theme}
开头钩子: {hook}
关键要点: {key_points}
结尾悬念: {ending_hook}

要求:
1. 承接第二段的悬念，在结尾彻底释放
2. 最后要有震撼的反转或情感高潮
3. 结尾可以是开放性结局，增加讨论度
4. 每句 estimated_duration_sec 控制在 3-6 秒
5. paragraph_text 要通顺流畅，适合直接配音
6. 总时长控制在 60-90 秒的解说长度""",
}


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口: 读取 outline.json → 生成3段 script"""
    scripts_dir = work_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)

    outline = json.loads((work_dir / "outline.json").read_text(encoding="utf-8"))

    for part in ["part1", "part2", "part3"]:
        output_path = scripts_dir / f"{part}.json"
        if output_path.exists():
            print(f"  {part}.json 已存在，跳过")
            continue

        section = outline[part]
        user_prompt = PART_PROMPTS[part].format(
            theme=section["theme"],
            hook=section["hook"],
            key_points="\n".join(f"- {kp}" for kp in section["key_points"]),
            ending_hook=section["ending_hook"],
        )

        print(f"  调用 MiniMax 生成 {part} 脚本...")
        result = call_structured("minimax", user_prompt, SYSTEM_PROMPT)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        num_sentences = len(result.get("sentences", []))
        print(f"  ✅ {part}: {num_sentences} 句 → {output_path}")
