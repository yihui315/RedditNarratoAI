"""
src/chapter_refine.py - 章节精化
─────────────────────────────────
输入: chapter_draft.json
输出: work_dir/chapter_refined.json

模型: gemma4 (Ollama)
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个资深影视编剧，负责精化电影解说章节结构。
读取章节草稿，优化每章的 summary 和 main_conflict，
并为每章打一个 importance_score (0~1，越重要越高)。
严格输出JSON，不要有额外文字。"""


USER_TEMPLATE = """请精化以下章节草稿：

{chapters_text}

要求:
1. 保持3章结构不变
2. 优化 summary，使其更有吸引力
3. 补充 main_conflict：每章的核心矛盾/冲突
4. 给出 importance_score (0~1)
5. 输出必须是合法的JSON对象，格式:
{{"chapters": [{{"id": 1, "summary": "...", "main_conflict": "...", "importance_score": 0.8}}]}}"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    output_path = work_dir / "chapter_refined.json"

    if output_path.exists():
        print(f"  chapter_refined.json 已存在，跳过")
        return

    draft = json.loads((work_dir / "chapter_draft.json").read_text(encoding="utf-8"))

    chapters_text = "\n".join(
        f"第{c['id']}章: {c['summary']}\n  人物: {', '.join(c.get('characters', []))}\n  关键事件: {', '.join(c.get('key_events', []))}"
        for c in draft["chapters"]
    )

    user_prompt = USER_TEMPLATE.format(chapters_text=chapters_text)

    print(f"  调用 gemma4 精化章节...")
    result = call_structured("gemma4", user_prompt, SYSTEM_PROMPT)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 章节精化完成 → {output_path}")
