"""
src/scene_prompt_refine.py - 镜头提示词精化（Gemma4）
──────────────────────────────────────────────────────
输入: scene_prompts/draft_{part}.json
输出: work_dir/scene_prompts/refined_{part}.json

模型: gemma4 (Ollama)
精化 HyDE 提示词，提升检索质量
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个AI视觉提示词专家，负责优化镜头检索提示词。
严格输出JSON，不要有任何额外文字。

输出格式:
{
  "scene_prompts": [
    {"sentence_id": 1, "prompt": "优化后的英文提示词"}
  ]
}"""


REFINE_TEMPLATE = """请优化以下镜头提示词，使其更适合AI视频/图片检索：

原始提示词:
{prompts_text}

要求:
1. 保持关键词数量 3-8 个
2. 优化用词，提升检索相关性
3. 添加更精准的情绪/氛围词
4. 确保英文语法正确
5. 保持 sentence_id 不变
6. 输出完整JSON数组"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    prompts_dir = work_dir / "scene_prompts"
    prompts_dir.mkdir(exist_ok=True)

    for part_name in ["part1", "part2", "part3"]:
        input_path  = prompts_dir / f"draft_{part_name}.json"
        output_path = prompts_dir / f"refined_{part_name}.json"

        if output_path.exists():
            print(f"  refined_{part_name}.json 已存在，跳过")
            continue

        if not input_path.exists():
            print(f"  ⚠️  {input_path} 不存在，跳过")
            continue

        draft = json.loads(input_path.read_text(encoding="utf-8"))
        prompts = draft.get("scene_prompts", [])

        prompts_text = "\n".join(
            f"句{p['sentence_id']}: {p['prompt']}"
            for p in prompts
        )

        user_prompt = REFINE_TEMPLATE.format(prompts_text=prompts_text)

        print(f"  调用 gemma4 精化 {part_name} 提示词...")
        result = call_structured("gemma4", user_prompt, SYSTEM_PROMPT)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {part_name} 提示词精化完成 → {output_path}")
