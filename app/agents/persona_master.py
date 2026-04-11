"""
Agent v4.0: PersonaMaster — 永久画像持久化Agent
首次运行通过LLM交互式采集用户画像（赛道、风格、变现路径、禁区），
并将结果持久化到 config/persona.json，后续运行自动加载。

所有下游Agent均可读取 persona 信息以保持风格一致。
"""

import json
import os
from typing import Any, Dict

from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config

PERSONA_PROMPT = """你是一位短视频内容操盘手。请根据以下信息，生成一份结构化的创作者画像。

## 用户提供的信息:
{user_input}

## 请用JSON格式输出（不要输出markdown代码块标记，直接输出JSON）:
{{
    "nickname": "创作者昵称",
    "niche": "主赛道（如：短剧解说/Reddit故事/影视解说）",
    "sub_niches": ["细分赛道1", "细分赛道2"],
    "target_audience": "目标受众画像",
    "tone": "语气风格（如：犀利吐槽/温暖治愈/悬疑烧脑）",
    "monetization": ["变现路径1", "变现路径2"],
    "forbidden_topics": ["禁区1", "禁区2"],
    "content_frequency": "日更/周更频率",
    "platforms": ["主要发布平台1", "平台2"],
    "signature_hooks": ["标志性钩子风格1", "风格2"],
    "brand_keywords": ["品牌关键词1", "关键词2"]
}}
"""

DEFAULT_PERSONA = {
    "nickname": "RedditNarratoAI",
    "niche": "短剧解说",
    "sub_niches": ["Reddit故事", "影视解说", "社会奇闻"],
    "target_audience": "18-35岁，喜欢追剧/刷短视频的年轻人",
    "tone": "犀利吐槽+悬疑感",
    "monetization": ["流量分成", "私域引流", "品牌合作"],
    "forbidden_topics": ["政治敏感", "未经证实的医疗建议", "暴力血腥"],
    "content_frequency": "日更3-5条",
    "platforms": ["tiktok", "youtube_shorts", "douyin"],
    "signature_hooks": ["反常识钩子", "悬念开场", "数字冲击"],
    "brand_keywords": ["爆款", "解说", "短剧", "故事"],
}


class PersonaMasterAgent(BaseAgent):
    """
    永久画像持久化Agent

    输入: user_input (首次采集) 或 无 (后续自动加载)
    输出: persona dict（已持久化到 config/persona.json）
    """

    def __init__(self, config: dict):
        super().__init__(config, name="PersonaMaster")
        self.persona_file = os.path.join(
            config.get("app", {}).get("root_dir", "."),
            "config",
            "persona.json",
        )

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            user_input (str): 用户自我描述（首次采集时需要）
            force_refresh (bool): 强制重新采集
        """
        force_refresh = input_data.get("force_refresh", False)

        # If persona exists and no force refresh, load from file
        if os.path.exists(self.persona_file) and not force_refresh:
            try:
                with open(self.persona_file, "r", encoding="utf-8") as f:
                    persona = json.load(f)
                logger.info(f"[PersonaMaster] 已加载画像: {self.persona_file}")
                return AgentResult(
                    success=True,
                    data={"persona": persona, "source": "cached"},
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[PersonaMaster] 读取画像失败，将重新生成: {e}")

        # Generate persona from user input or use defaults
        user_input = input_data.get("user_input", "")
        if user_input:
            persona = self._generate_persona(user_input)
        else:
            logger.info("[PersonaMaster] 无用户输入，使用默认画像")
            persona = DEFAULT_PERSONA.copy()

        # Persist to file
        self._save_persona(persona)

        return AgentResult(
            success=True,
            data={
                "persona": persona,
                "source": "generated" if user_input else "default",
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: persona 必须包含 niche 和 tone"""
        if not result.success:
            return False
        persona = result.data.get("persona", {})
        return bool(persona.get("niche")) and bool(persona.get("tone"))

    def _generate_persona(self, user_input: str) -> dict:
        """通过LLM生成结构化画像"""
        prompt = PERSONA_PROMPT.format(user_input=user_input)
        try:
            raw = generate_response_from_config(prompt, self.config)
            if raw:
                persona = self._parse_json(raw)
                if persona and persona.get("niche"):
                    return persona
        except Exception as e:
            logger.error(f"[PersonaMaster] LLM生成画像失败: {e}")

        # Fallback to defaults
        logger.info("[PersonaMaster] LLM不可用，使用默认画像")
        return DEFAULT_PERSONA.copy()

    def _save_persona(self, persona: dict):
        """持久化画像到JSON文件"""
        try:
            os.makedirs(os.path.dirname(self.persona_file), exist_ok=True)
            with open(self.persona_file, "w", encoding="utf-8") as f:
                json.dump(persona, f, ensure_ascii=False, indent=2)
            logger.info(f"[PersonaMaster] 画像已保存: {self.persona_file}")
        except IOError as e:
            logger.error(f"[PersonaMaster] 保存画像失败: {e}")

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
