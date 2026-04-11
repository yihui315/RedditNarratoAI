"""
Agent: CharacterGenAgent (v5.0)
从主题/剧本自动生成角色库：形象描述、音色特征、性格标签
灵感来源: huobao-drama 角色生成系统

输入: theme/script → LLM生成角色列表
输出: characters JSON数组（每个角色含name/appearance/voice_id/personality）
优雅降级: LLM调用失败时返回默认角色模板
"""

import json
from typing import Any, Dict, List
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


# 默认角色模板（LLM不可用时的优雅降级）
DEFAULT_CHARACTERS = [
    {
        "name": "主角",
        "role": "protagonist",
        "appearance": "普通外表，眼神坚毅",
        "voice_id": "narrator_default",
        "personality": "隐忍、善良、关键时刻爆发",
        "age_range": "20-30",
    },
    {
        "name": "反派",
        "role": "antagonist",
        "appearance": "衣着光鲜，表情阴险",
        "voice_id": "villain_default",
        "personality": "傲慢、狡诈、欺软怕硬",
        "age_range": "25-40",
    },
]


class CharacterGenAgent(BaseAgent):
    """
    角色生成Agent (v5.0)

    从主题或剧本中自动提取/生成角色信息，
    为后续分镜、配音、AI视频生成提供角色一致性基础。
    """

    def __init__(self, config: dict):
        super().__init__(config, name="CharacterGen")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            theme (str): 主题描述（如 "复仇短剧 女主被渣男抛弃"）
            script (str): 已有剧本文本（可选，用于提取角色）
            max_characters (int): 最多生成几个角色（默认5）
        """
        theme = input_data.get("theme", "")
        script = input_data.get("script", "")
        max_characters = input_data.get("max_characters", 5)

        if not theme and not script:
            return AgentResult(
                success=False,
                error="缺少主题(theme)或剧本(script)输入",
            )

        source_text = script if script else theme

        # 尝试LLM生成角色
        try:
            from app.services.llm import generate_response_from_config

            prompt = self._build_prompt(source_text, max_characters)
            response = generate_response_from_config(
                prompt=prompt,
                config_dict=self.config,
                system_prompt="你是专业的短剧角色设计师，擅长创造有记忆点的角色。",
            )
            characters = self._parse_characters(response)
            if characters:
                return AgentResult(
                    success=True,
                    data={"characters": characters[:max_characters]},
                )
        except Exception as e:
            logger.warning(f"[CharacterGen] LLM生成角色失败，使用默认模板: {e}")

        # 降级：返回默认角色
        return AgentResult(
            success=True,
            data={
                "characters": DEFAULT_CHARACTERS,
                "fallback": True,
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 至少有1个角色，每个角色有name和role"""
        if not result.success:
            return False
        characters = result.data.get("characters", [])
        if not characters:
            return False
        return all(
            c.get("name") and c.get("role")
            for c in characters
        )

    def _build_prompt(self, source_text: str, max_characters: int) -> str:
        return f"""分析以下内容，生成{max_characters}个以内的角色设定。

内容：
{source_text[:2000]}

请以JSON数组格式输出，每个角色包含以下字段：
- name: 角色名称
- role: 角色类型（protagonist/antagonist/supporting/narrator）
- appearance: 外貌描述（用于AI生图提示词）
- voice_id: 音色标签（如 warm_female / cold_male / narrator_default）
- personality: 性格关键词
- age_range: 年龄范围

输出格式:
```json
[{{"name": "...", "role": "...", "appearance": "...", "voice_id": "...", "personality": "...", "age_range": "..."}}]
```"""

    def _parse_characters(self, response: str) -> List[Dict]:
        """从LLM响应中解析角色JSON"""
        # 尝试直接解析
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从代码块中解析
        import re
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if code_block:
            try:
                data = json.loads(code_block.group(1))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        # 尝试找到JSON数组
        bracket_match = re.search(r"\[.*\]", response, re.DOTALL)
        if bracket_match:
            try:
                data = json.loads(bracket_match.group(0))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        return []
