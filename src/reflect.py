"""
src/reflect.py - 脚本自检与修复（DeepSeek）
────────────────────────────────────────────
输入: scripts/script_part{N}.json (每段)
输出: work_dir/scripts/reflect_part{N}.json

模型: DeepSeek API
流程: 读取初稿 → 自我审查 → 改进脚本
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个严格的电影解说编辑，负责自我审查和修正解说脚本。
找出脚本中的问题并输出修正后的完整脚本。
严格输出JSON，不要有任何额外文字。

输出格式:
{
  "issues": ["问题1", "问题2"],
  "improved_script": {
    "paragraph_text": "修正后的完整文本",
    "sentences": [{"id": 1, "text": "...", "estimated_duration_sec": 4}]
  }
}
issues 可以为空数组（如果没问题）。"""


REVIEW_TEMPLATE = """请审查以下解说脚本，找出潜在问题：

【第{part_num}段 - {theme}】

段落文本:
{paragraph_text}

逐句内容:
{sentences_text}

请检查:
1. 是否有逻辑不通或跳跃的地方？
2. 是否有语法/用词问题？
3. 是否有过于平淡、缺乏情绪的地方？
4. 开头钩子和结尾悬念是否足够强？
5. 是否有冗余重复的内容？
6. 时长估计是否合理？

如果没有问题，issues 为空数组。"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口: 遍历 scripts/ 下所有 script_part{N}.json → 自检 → 保存"""
    scripts_dir = work_dir / "scripts"
    outline = json.loads((work_dir / "outline.json").read_text(encoding="utf-8"))

    for part_name in ["part1", "part2", "part3"]:
        input_path  = scripts_dir / f"{part_name}.json"
        output_path = scripts_dir / f"reflect_{part_name}.json"

        if output_path.exists():
            print(f"  reflect_{part_name}.json 已存在，跳过")
            continue

        if not input_path.exists():
            print(f"  ⚠️  {input_path} 不存在，跳过")
            continue

        script = json.loads(input_path.read_text(encoding="utf-8"))
        section = outline[part_name]

        sentences_text = "\n".join(
            f"句{i+1} [{s['estimated_duration_sec']}s]: {s['text']}"
            for i, s in enumerate(script.get("sentences", []))
        )

        user_prompt = REVIEW_TEMPLATE.format(
            part_num=part_name.replace("part", ""),
            theme=section["theme"],
            paragraph_text=script.get("paragraph_text", ""),
            sentences_text=sentences_text,
        )

        print(f"  调用 DeepSeek 审查 {part_name}...")
        result = call_structured("deepseek", user_prompt, SYSTEM_PROMPT)

        # 保存审查结果
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        issues = result.get("issues", [])
        print(f"  ✅ {part_name}: 发现 {len(issues)} 个问题 → {output_path}")
        if issues:
            for iss in issues:
                print(f"     • {iss}")
