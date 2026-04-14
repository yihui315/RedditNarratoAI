"""
src/outline.py - 三段式解说大纲生成
────────────────────────────────────
输入: chapter_refined.json
输出: work_dir/outline.json

模型: DeepSeek API
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_deepseek, call_structured


SYSTEM_PROMPT = """你是一个顶级的电影解说策划专家。
根据章节分析，生成一套"爆款"三段式解说大纲。
严格输出JSON，不要有任何额外文字。"""


USER_TEMPLATE = """请为以下电影生成三段式解说大纲：

电影类型/题材: {genre}
总章节数: {num_chapters}

章节精化内容:
{chapters_text}

要求:
1. 三段对应"开头(吸引眼球)、中段(层层递进)、结尾(震撼收尾)"
2. 每段必须包含: theme(主题), hook(开头钩子), key_points(3-5个要点), ending_hook(结尾悬念)
3. hook 要能在3秒内抓住观众
4. ending_hook 要能让观众想看下一段
5. 风格要有反转/悬念/情绪波动
6. 输出格式严格遵循:
{{"part1": {{"theme": "...", "hook": "...", "key_points": [...], "ending_hook": "..."}}}},
{{"part2": ...}}, {{"part3": ...}}"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    output_path = work_dir / "outline.json"

    if output_path.exists():
        print(f"  outline.json 已存在，跳过")
        return

    refined = json.loads((work_dir / "chapter_refined.json").read_text(encoding="utf-8"))
    chapters = refined["chapters"]

    chapters_text = "\n".join(
        f"第{c['id']}章 | 重要性:{c['importance_score']} | 核心冲突:{c['main_conflict']}\n  {c['summary']}"
        for c in chapters
    )

    genre = refined.get("genre", "悬疑/剧情")
    user_prompt = USER_TEMPLATE.format(
        genre=genre,
        num_chapters=len(chapters),
        chapters_text=chapters_text,
    )

    print(f"  调用 DeepSeek 生成三段式大纲...")
    result = call_structured("deepseek", user_prompt, SYSTEM_PROMPT)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 三段式大纲完成 → {output_path}")
