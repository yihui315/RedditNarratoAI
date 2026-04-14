"""
src/scene_prompt_draft.py - 镜头提示词生成（HyDE, MiniMax）
──────────────────────────────────────────────────────────────
输入: final_scripts/final_{part}.json
输出: work_dir/scene_prompts/draft_{part}.json

模型: MiniMax API
为每句旁白生成"理想镜头描述"，用于后续图/视频检索

这是 HyDE (Hypothetical Document Embeddings) 策略：
让LLM先想象匹配这段话的理想视觉画面，再做检索
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.llm_client import call_structured


SYSTEM_PROMPT = """你是一个专业的影视分镜师，负责为解说旁白生成镜头检索提示词。
严格输出JSON，不要有任何额外文字。

每条提示词格式:
{
  "sentence_id": 1,
  "prompt": "英文短句，描述理想匹配画面，用空格分隔关键词"
}

提示词要求:
- 英文
- 3-8个关键词: 主体 + 动作 + 场景 + 情绪 + 镜头类型
- 例如: "woman shocked close-up indoor emotional cinematic"
- 不要使用完整句子，只要关键词串"""


PROMPT_TEMPLATE = """请为以下解说脚本的每句话生成"理想镜头描述"（用于AI视频/图片检索）：

段落: {paragraph_text}

逐句内容:
{sentences_text}

要求:
1. 为每句话生成一条 prompt
2. prompt 用英文，3-8个关键词
3. 关键词覆盖: 主体(谁) + 动作/表情 + 场景 + 情绪 + 镜头类型
4. 示例: "man screaming close-up dark-room terror cinematic"
5. 严格输出JSON数组格式:
{{"scene_prompts": [{{"sentence_id": 1, "prompt": "..."}}]}}"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    final_dir   = work_dir / "final_scripts"
    prompts_dir = work_dir / "scene_prompts"
    prompts_dir.mkdir(exist_ok=True)

    for part_name in ["part1", "part2", "part3"]:
        input_path  = final_dir / f"final_{part_name}.json"
        output_path = prompts_dir / f"draft_{part_name}.json"

        if output_path.exists():
            print(f"  draft_{part_name}.json 已存在，跳过")
            continue

        if not input_path.exists():
            print(f"  ⚠️  {input_path} 不存在，跳过")
            continue

        script = json.loads(input_path.read_text(encoding="utf-8"))
        sentences = script.get("sentences", [])

        paragraph_text = " ".join(s["text"] for s in sentences)
        sentences_text = "\n".join(
            f"句{i+1}: {s['text']}"
            for i, s in enumerate(sentences)
        )

        user_prompt = PROMPT_TEMPLATE.format(
            paragraph_text=paragraph_text,
            sentences_text=sentences_text,
        )

        print(f"  调用 MiniMax 生成 {part_name} 镜头提示...")
        result = call_structured("minimax", user_prompt, SYSTEM_PROMPT)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        num_prompts = len(result.get("scene_prompts", []))
        print(f"  ✅ {part_name}: {num_prompts} 条提示 → {output_path}")
