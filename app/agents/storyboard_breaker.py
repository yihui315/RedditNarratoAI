"""
Agent: StoryboardBreakerAgent (v5.0)
将剧本拆解为分镜序列，每镜含场景描述、镜头类型、时长、AI生图/生视频Prompt
灵感来源: huobao-drama 分镜拆解 + Toonflow 无限画布分镜逻辑

输入: script + characters → LLM拆解为分镜
输出: storyboard JSON数组（每镜含scene/shot_type/duration/prompt/character）
优雅降级: LLM不可用时按段落自动切分
"""

import json
import re
from typing import Any, Dict, List
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class StoryboardBreakerAgent(BaseAgent):
    """
    分镜拆解Agent (v5.0)

    将完整剧本拆解为分镜序列，每个分镜包含：
    - 场景描述（用于AI生图/生视频）
    - 镜头类型（特写/中景/远景/运动镜头）
    - 时长（秒）
    - AI生成Prompt
    - 涉及角色
    """

    SHOT_TYPES = [
        "close_up",      # 特写
        "medium_shot",   # 中景
        "wide_shot",     # 远景
        "tracking",      # 跟踪镜头
        "pov",           # 第一人称
        "establishing",  # 建立镜头
    ]

    def __init__(self, config: dict):
        super().__init__(config, name="StoryboardBreaker")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 剧本/文案文本
            characters (list): 角色列表（来自CharacterGenAgent）
            target_duration (int): 目标总时长秒数（默认60）
        """
        script = input_data.get("script", "")
        characters = input_data.get("characters", [])
        target_duration = input_data.get("target_duration", 60)

        if not script:
            return AgentResult(
                success=False,
                error="缺少剧本(script)输入",
            )

        # 尝试LLM拆解
        try:
            from app.services.llm import generate_response_from_config

            prompt = self._build_prompt(script, characters, target_duration)
            response = generate_response_from_config(
                prompt=prompt,
                config_dict=self.config,
                system_prompt="你是专业的短剧分镜师，擅长将文字剧本转化为视觉分镜。",
            )
            storyboard = self._parse_storyboard(response)
            if storyboard:
                return AgentResult(
                    success=True,
                    data={"storyboard": storyboard},
                )
        except Exception as e:
            logger.warning(f"[StoryboardBreaker] LLM分镜失败，使用自动切分: {e}")

        # 降级：按段落自动切分
        storyboard = self._auto_split(script, target_duration)
        return AgentResult(
            success=True,
            data={
                "storyboard": storyboard,
                "fallback": True,
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 至少2个分镜，每个分镜有scene和duration"""
        if not result.success:
            return False
        storyboard = result.data.get("storyboard", [])
        if len(storyboard) < 2:
            return False
        return all(
            s.get("scene") and s.get("duration", 0) > 0
            for s in storyboard
        )

    def _build_prompt(
        self, script: str, characters: list, target_duration: int
    ) -> str:
        char_desc = ""
        if characters:
            char_desc = "角色列表:\n" + "\n".join(
                f"- {c.get('name', '?')}: {c.get('appearance', '')}"
                for c in characters
            )

        return f"""将以下剧本拆解为分镜序列，目标总时长约{target_duration}秒。

剧本：
{script[:3000]}

{char_desc}

请以JSON数组格式输出分镜，每个分镜包含：
- scene: 场景描述（中文，清晰描述画面内容）
- shot_type: 镜头类型（close_up/medium_shot/wide_shot/tracking/pov/establishing）
- duration: 时长（秒，整数）
- prompt: AI生图/生视频英文Prompt（用于Stable Diffusion/Kling/Runway）
- character: 涉及角色名称（可选）
- emotion: 情绪氛围（如 tense/warm/shocking）

输出格式:
```json
[{{"scene": "...", "shot_type": "...", "duration": 5, "prompt": "...", "character": "...", "emotion": "..."}}]
```"""

    def _parse_storyboard(self, response: str) -> List[Dict]:
        """从LLM响应中解析分镜JSON"""
        # 直接解析
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # 代码块解析
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if code_block:
            try:
                data = json.loads(code_block.group(1))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        # 查找JSON数组
        bracket_match = re.search(r"\[.*\]", response, re.DOTALL)
        if bracket_match:
            try:
                data = json.loads(bracket_match.group(0))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

        return []

    def _auto_split(self, script: str, target_duration: int) -> List[Dict]:
        """降级方案：按段落/句子自动切分为分镜"""
        # 按换行 + 句号切分
        sentences = [s.strip() for s in re.split(r"[。！？\n]+", script) if s.strip()]
        if not sentences:
            sentences = [script[:200]]

        # 均匀分配时长
        per_scene_duration = max(3, target_duration // max(len(sentences), 1))
        shot_cycle = self.SHOT_TYPES

        storyboard = []
        for i, sentence in enumerate(sentences):
            storyboard.append({
                "scene": sentence[:100],
                "shot_type": shot_cycle[i % len(shot_cycle)],
                "duration": per_scene_duration,
                "prompt": f"cinematic scene: {sentence[:80]}",
                "character": "",
                "emotion": "neutral",
            })

        return storyboard
