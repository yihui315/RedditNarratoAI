"""
Agent v4.0: CompetitorDecode — 竞品拆解Agent
自动拆解竞品文案的框架、情绪曲线、钩子公式，
并将提取的公式存入 config/formula-library.json 和 config/hooks-library.json

灵感来源: binghe Agent 的 ~decode 功能
"""

import json
import os
from typing import Any, Dict, List

from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config


DECODE_PROMPT = """你现在是短剧解说/Reddit故事百万播放拆解专家。

## 竞品文案:
{competitor_text}

## 请深度拆解并用JSON格式输出（不要输出markdown代码块标记，直接输出JSON）:
{{
    "structure": {{
        "hook": "开头钩子（前3秒文案）",
        "setup": "铺垫段（背景/人物建立）",
        "core": "核心冲突段（高潮）",
        "closure": "收束段（结尾/悬念/CTA）"
    }},
    "emotion_curve": [
        {{"timestamp": "0-3s", "emotion": "好奇/震惊", "intensity": 8}},
        {{"timestamp": "3-15s", "emotion": "紧张", "intensity": 6}},
        {{"timestamp": "15-40s", "emotion": "愤怒/感动", "intensity": 9}},
        {{"timestamp": "40-60s", "emotion": "意外/期待", "intensity": 10}}
    ],
    "golden_lines": ["金句1", "金句2", "金句3"],
    "hook_formula": {{
        "name": "公式名称（如：反常识钩子/数字冲击/身份反转）",
        "template": "公式模板（如：别人都以为...其实...）",
        "example": "具体例子"
    }},
    "transferable_angles": [
        "迁移角度1：可以用于我们赛道的改编方向",
        "迁移角度2",
        "迁移角度3"
    ],
    "viral_score": 8,
    "improvement_suggestions": ["改进建议1", "改进建议2"]
}}
"""


class CompetitorDecodeAgent(BaseAgent):
    """
    竞品拆解Agent

    输入: 竞品文案文本
    输出: 拆解报告 + 自动更新公式库/钩子库
    """

    def __init__(self, config: dict):
        super().__init__(config, name="CompetitorDecode")
        root_dir = config.get("app", {}).get("root_dir", ".")
        self.formula_file = os.path.join(root_dir, "config", "formula-library.json")
        self.hooks_file = os.path.join(root_dir, "config", "hooks-library.json")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            competitor_text (str): 竞品文案文本
            source (str): 来源（reddit/douyin/youtube）
        """
        competitor_text = input_data.get("competitor_text", "")
        if not competitor_text:
            return AgentResult(success=False, error="缺少竞品文案文本")

        source = input_data.get("source", "unknown")

        try:
            prompt = DECODE_PROMPT.format(competitor_text=competitor_text)
            raw = generate_response_from_config(prompt, self.config)
            if not raw:
                return AgentResult(success=False, error="LLM返回空响应")

            decode_result = self._parse_json(raw)
            if not decode_result:
                return AgentResult(success=False, error="无法解析拆解结果")

            decode_result["source"] = source

            # Auto-update formula and hooks libraries
            self._update_formula_library(decode_result)
            self._update_hooks_library(decode_result)

            return AgentResult(
                success=True,
                data={
                    "decode": decode_result,
                    "formula_file": self.formula_file,
                    "hooks_file": self.hooks_file,
                },
            )

        except Exception as e:
            logger.error(f"[CompetitorDecode] 拆解失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 拆解结果必须包含 structure 和 hook_formula"""
        if not result.success:
            return False
        decode = result.data.get("decode", {})
        return bool(decode.get("structure")) and bool(decode.get("hook_formula"))

    def _update_formula_library(self, decode: dict):
        """将新发现的公式追加到 formula-library.json"""
        formula = decode.get("hook_formula", {})
        if not formula or not formula.get("name"):
            return

        library = self._load_json_file(self.formula_file, {"formulas": []})
        existing_names = {f.get("name") for f in library.get("formulas", [])}

        if formula["name"] not in existing_names:
            library["formulas"].append(formula)
            self._save_json_file(self.formula_file, library)
            logger.info(
                f"[CompetitorDecode] 新公式入库: {formula['name']}"
            )

    def _update_hooks_library(self, decode: dict):
        """将金句和钩子追加到 hooks-library.json"""
        golden_lines = decode.get("golden_lines", [])
        structure = decode.get("structure", {})
        hook = structure.get("hook", "")

        library = self._load_json_file(
            self.hooks_file, {"hooks": [], "golden_lines": []}
        )

        if hook and hook not in library.get("hooks", []):
            library["hooks"].append(hook)

        existing_lines = set(library.get("golden_lines", []))
        for line in golden_lines:
            if line and line not in existing_lines:
                library["golden_lines"].append(line)

        self._save_json_file(self.hooks_file, library)

    @staticmethod
    def _load_json_file(path: str, default: dict) -> dict:
        """安全加载JSON文件"""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return default.copy()

    @staticmethod
    def _save_json_file(path: str, data: dict):
        """安全写入JSON文件"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"写入文件失败 {path}: {e}")

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从LLM响应中提取JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        import re
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass
        return {}
