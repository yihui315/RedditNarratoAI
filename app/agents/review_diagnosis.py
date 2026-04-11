"""
Agent v4.0: ReviewDiagnosis — 质量诊断与爆款评分Agent
5维度评分体系:
  1. 钩子强度 (Hook Power)
  2. 情绪曲线完整度 (Emotion Arc)
  3. 节奏与时长 (Pacing)
  4. SEO/算法友好度 (Algorithm Fit)
  5. 转化路径清晰度 (Conversion Clarity) ← v4.0新增

灵感来源: binghe Agent 的 ~review 功能
"""

import json
from typing import Any, Dict

from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config


REVIEW_PROMPT = """你是一位短视频数据专家，已分析过10000+爆款视频。

## 待诊断文案:
{script}

## 视频元数据:
标题: {title}
时长: {duration}秒
平台: {platforms}

## 创作者画像:
{persona_json}

## 请从5个维度严格评分（1-10分），并给出诊断建议。
用JSON格式输出（不要输出markdown代码块标记，直接输出JSON）:
{{
    "scores": {{
        "hook_power": {{
            "score": 8,
            "reason": "开头3秒分析",
            "suggestion": "改进建议"
        }},
        "emotion_arc": {{
            "score": 7,
            "reason": "情绪曲线分析",
            "suggestion": "改进建议"
        }},
        "pacing": {{
            "score": 8,
            "reason": "节奏与时长分析",
            "suggestion": "改进建议"
        }},
        "algorithm_fit": {{
            "score": 7,
            "reason": "SEO/算法友好度分析",
            "suggestion": "改进建议"
        }},
        "conversion_clarity": {{
            "score": 6,
            "reason": "转化路径分析（关注/点赞/评论引导是否清晰）",
            "suggestion": "改进建议"
        }}
    }},
    "overall_score": 7.2,
    "viral_probability": "72%",
    "top_issues": ["最需要改进的问题1", "问题2"],
    "rewrite_suggestions": ["具体修改建议1", "建议2", "建议3"],
    "comment_bait": "建议的评论引导语（引发互动的问题）"
}}
"""


class ReviewDiagnosisAgent(BaseAgent):
    """
    质量诊断与爆款评分Agent

    输入: 文案 + 元数据
    输出: 5维度评分 + 改进建议
    """

    def __init__(self, config: dict):
        super().__init__(config, name="ReviewDiagnosis")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            script (str): 解说文案
            title (str): 视频标题
            duration (int): 预估时长(秒)
            persona (dict): 创作者画像
            platforms (list): 发布平台
        """
        script = input_data.get("script", "")
        if not script:
            return AgentResult(success=False, error="缺少待诊断文案")

        title = input_data.get("title", "未知标题")
        duration = input_data.get("duration", 60)
        persona = input_data.get("persona", {})
        platforms = input_data.get("platforms", ["tiktok", "youtube_shorts"])

        persona_json = (
            json.dumps(persona, ensure_ascii=False, indent=2)
            if persona
            else "{}"
        )

        prompt = REVIEW_PROMPT.format(
            script=script,
            title=title,
            duration=duration,
            platforms=", ".join(platforms),
            persona_json=persona_json,
        )

        try:
            raw = generate_response_from_config(prompt, self.config)
            if not raw:
                return AgentResult(success=False, error="LLM返回空响应")

            review = self._parse_json(raw)
            if not review or not review.get("scores"):
                return AgentResult(success=False, error="无法解析诊断结果")

            # Calculate overall if not provided
            if not review.get("overall_score"):
                scores = review["scores"]
                total = sum(
                    s.get("score", 0)
                    for s in scores.values()
                    if isinstance(s, dict)
                )
                count = sum(
                    1
                    for s in scores.values()
                    if isinstance(s, dict) and "score" in s
                )
                review["overall_score"] = round(total / max(count, 1), 1)

            return AgentResult(
                success=True,
                data={"review": review},
            )

        except Exception as e:
            logger.error(f"[ReviewDiagnosis] 诊断失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 诊断必须包含scores和overall_score"""
        if not result.success:
            return False
        review = result.data.get("review", {})
        scores = review.get("scores", {})
        has_scores = len(scores) >= 3
        has_overall = review.get("overall_score") is not None
        return has_scores and has_overall

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
