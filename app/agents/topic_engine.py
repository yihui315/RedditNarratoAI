"""
Agent v4.0: TopicEngine — 多模式选题引擎
支持4种选题模式:
  --mine   : 从已有素材库/历史数据中挖掘新角度
  --hot    : 从Reddit/YouTube热榜实时抓取热门话题
  --rival  : 从竞品账号分析热门选题
  --flash  : 追热点快速选题（突发事件/节日/热搜）

灵感来源: binghe Agent 的 ~topics 功能
"""

import json
import time
from typing import Any, Dict, List

from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config


TOPIC_PROMPT = """你是一位百万粉丝短视频选题专家，精通Reddit故事/短剧解说赛道。

## 创作者画像:
{persona_json}

## 选题模式: {mode}
## 附加信息: {context}

## 请生成7个爆款选题，用JSON格式输出（不要输出markdown代码块标记，直接输出JSON）:
{{
    "topics": [
        {{
            "title": "选题标题（20字以内）",
            "angle": "独特切入角度",
            "hook": "前3秒钩子文案",
            "target_emotion": "目标情绪（好奇/愤怒/感动/震惊/搞笑）",
            "estimated_viral_score": 8,
            "reference": "参考素材/来源",
            "tags": ["标签1", "标签2"]
        }}
    ],
    "strategy_note": "本批选题策略说明（50字以内）"
}}
"""

MODE_CONTEXTS = {
    "mine": "从已有内容库和历史爆款中挖掘新角度，避免重复，寻找差异化切入点",
    "hot": "聚焦Reddit/YouTube当前热门话题，选择有争议性、情绪冲突强的内容",
    "rival": "分析竞品账号的高播放量内容，找到可迁移的选题框架和钩子公式",
    "flash": "追踪最新热点事件/节日/热搜，快速产出时效性选题",
}


class TopicEngineAgent(BaseAgent):
    """
    多模式选题引擎Agent

    输入: 选题模式 + 可选上下文
    输出: 7个爆款选题方案
    """

    def __init__(self, config: dict):
        super().__init__(config, name="TopicEngine")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            mode (str): 选题模式 (mine/hot/rival/flash)
            persona (dict): 创作者画像（可选，从PersonaMaster获取）
            context (str): 附加上下文/关键词
            rival_content (list): 竞品内容列表（rival模式需要）
            history (list): 历史选题列表（mine模式用于去重）
        """
        mode = input_data.get("mode", "hot")
        if mode not in MODE_CONTEXTS:
            mode = "hot"

        persona = input_data.get("persona", {})
        context = input_data.get("context", "")
        rival_content = input_data.get("rival_content", [])
        history = input_data.get("history", [])

        # Build context based on mode
        full_context = MODE_CONTEXTS[mode]
        if context:
            full_context += f"\n用户补充: {context}"
        if rival_content:
            full_context += f"\n竞品内容样本: {json.dumps(rival_content[:5], ensure_ascii=False)}"
        if history:
            full_context += f"\n已有选题(避免重复): {json.dumps(history[:10], ensure_ascii=False)}"

        persona_json = json.dumps(persona, ensure_ascii=False, indent=2) if persona else "{}"

        prompt = TOPIC_PROMPT.format(
            persona_json=persona_json,
            mode=mode,
            context=full_context,
        )

        try:
            raw = generate_response_from_config(prompt, self.config)
            if not raw:
                return AgentResult(success=False, error="LLM返回空响应")

            topics_data = self._parse_json(raw)
            if not topics_data or not topics_data.get("topics"):
                return AgentResult(success=False, error="无法解析选题结果")

            return AgentResult(
                success=True,
                data={
                    "topics": topics_data["topics"],
                    "strategy_note": topics_data.get("strategy_note", ""),
                    "mode": mode,
                    "count": len(topics_data["topics"]),
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

        except Exception as e:
            logger.error(f"[TopicEngine] 选题生成失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 至少生成3个选题，每个选题必须有title和hook"""
        if not result.success:
            return False
        topics = result.data.get("topics", [])
        if len(topics) < 3:
            logger.warning(f"[TopicEngine] 选题太少: {len(topics)}个")
            return False
        for t in topics:
            if not t.get("title") or not t.get("hook"):
                logger.warning(f"[TopicEngine] 选题缺少title或hook")
                return False
        return True

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
