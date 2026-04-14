"""
src/repair.py - 脚本修复（Gemma4）
───────────────────────────────────
输入: scripts/reflect_{part}.json
输出: work_dir/final_scripts/final_{part}.json

模型: gemma4 (Ollama)
流程: 读取自检结果 → 如果有问题 → Gemma4生成修正版
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个电影解说编剧，负责根据审查意见修正脚本。
严格输出JSON，不要有任何额外文字。

输出格式:
{
  "sentences": [
    {"id": 1, "text": "修正后的句子", "duration": 4}
  ]
}"""


REPAIR_TEMPLATE = """请根据以下审查意见修正脚本：

原始脚本:
{original_text}

逐句内容:
{sentences_text}

审查发现的问题:
{issues_text}

要求:
1. 修正所有发现的问题
2. 保持原有句子的核心意思不变
3. 提升语言质量和情绪感染力
4. 确保时长估计合理（3-6秒/句）
5. 输出完整的修正后脚本（sentences 数组）"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    scripts_dir   = work_dir / "scripts"
    final_dir    = work_dir / "final_scripts"
    final_dir.mkdir(exist_ok=True)

    for part_name in ["part1", "part2", "part3"]:
        input_path  = scripts_dir / f"reflect_{part_name}.json"
        output_path = final_dir / f"final_{part_name}.json"

        if output_path.exists():
            print(f"  final_{part_name}.json 已存在，跳过")
            continue

        if not input_path.exists():
            print(f"  ⚠️  {input_path} 不存在，跳过")
            continue

        reflect = json.loads(input_path.read_text(encoding="utf-8"))
        issues  = reflect.get("issues", [])

        # 如果没有发现问题，直接用 improved_script
        if not issues:
            improved = reflect.get("improved_script", {})
            sentences = improved.get("sentences", [])
            if sentences:
                print(f"  ✅ {part_name}: 无问题，直接保存")
                _save_final(output_path, sentences)
                continue
            # 如果没有 improved_script，用原始脚本
            original = json.loads((scripts_dir / f"{part_name}.json").read_text(encoding="utf-8"))
            sentences = original.get("sentences", [])
            if sentences:
                print(f"  ✅ {part_name}: 无审查结果，使用原始脚本")
                _save_final(output_path, sentences)
                continue

        # 有问题，调用 gemma4 修复
        original = json.loads((scripts_dir / f"{part_name}.json").read_text(encoding="utf-8"))

        sentences_text = "\n".join(
            f"句{i+1} [{s.get('estimated_duration_sec', s.get('duration', 4))}s]: {s['text']}"
            for i, s in enumerate(original.get("sentences", []))
        )
        issues_text = "\n".join(f"- {iss}" for iss in issues) if issues else "（无）"

        user_prompt = REPAIR_TEMPLATE.format(
            original_text=original.get("paragraph_text", ""),
            sentences_text=sentences_text,
            issues_text=issues_text,
        )

        print(f"  调用 gemma4 修复 {part_name}...")
        result = call_structured("gemma4", user_prompt, SYSTEM_PROMPT)
        sentences = result.get("sentences", [])

        _save_final(output_path, sentences)
        print(f"  ✅ {part_name}: 修复完成 → {output_path}")


def _save_final(output_path: Path, sentences: list) -> None:
    """保存最终脚本"""
    output_path.parent.mkdir(exist_ok=True, parents=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"sentences": sentences}, f, ensure_ascii=False, indent=2)
