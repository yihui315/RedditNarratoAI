"""
Agent 8: SEO优化Agent（SEO Agent）
自动生成标题、描述、标签、缩略图建议，优化各平台分发效果
"""

import json
from typing import Any, Dict
from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config


SEO_PROMPT = """你是一位专业的短视频SEO优化师，精通TikTok/YouTube Shorts/Instagram Reels的算法。

## 视频信息:
标题: {title}
类型: {genre}
剧情摘要: {summary}
目标平台: {platforms}

## 要求:
请用JSON格式输出以下SEO优化方案（不要输出markdown代码块标记，直接输出JSON）:
{{
    "seo_title": "优化后的标题（20字以内，含核心关键词+情绪词）",
    "description": "视频描述（100字以内，含3-5个核心关键词）",
    "tags": ["标签1", "标签2", "...(15-20个热门标签)"],
    "hashtags": ["#话题1", "#话题2", "...(5-8个热门话题标签)"],
    "thumbnail_text": "缩略图上的文字（6字以内，冲击力最强的一句）",
    "best_post_time": "建议发布时间（如：周五 20:00）",
    "hook_description": "前3秒钩子描述（用于缩略图/预览）"
}}
"""


class SEOAgent(BaseAgent):
    """
    SEO优化Agent

    输入: 视频标题 + 剧情分析
    输出: SEO优化方案（标题/描述/标签/缩略图建议）
    """

    def __init__(self, config: dict):
        super().__init__(config, name="SEOAgent")
        publish_cfg = config.get("publish", {})
        self.platforms = publish_cfg.get(
            "platforms", ["tiktok", "youtube_shorts"]
        )

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            title (str): 视频标题
            analysis (dict): 剧情分析
            script (str): 解说文案（可选，用于提取关键词）
        """
        title = input_data.get("title", "")
        analysis = input_data.get("analysis", {})

        if not title and not analysis:
            return AgentResult(success=False, error="缺少标题或剧情分析")

        genre = analysis.get("genre", "短剧")
        summary = analysis.get("summary", "")
        platforms_str = ", ".join(self.platforms)

        prompt = SEO_PROMPT.format(
            title=title,
            genre=genre,
            summary=summary,
            platforms=platforms_str,
        )

        try:
            raw = generate_response_from_config(prompt, self.config)
            if not raw:
                return AgentResult(success=False, error="LLM返回空响应")

            seo_data = self._parse_json(raw)
            if not seo_data:
                # Fallback: generate basic SEO data
                seo_data = self._fallback_seo(title, genre, analysis)

            return AgentResult(
                success=True,
                data={
                    "seo": seo_data,
                    "raw_response": raw,
                },
            )

        except Exception as e:
            logger.error(f"[SEOAgent] SEO生成失败: {e}")
            # Fallback to basic SEO
            seo_data = self._fallback_seo(title, genre, analysis)
            return AgentResult(
                success=True,
                data={"seo": seo_data, "fallback": True},
            )

    def verify(self, result: AgentResult) -> bool:
        """验证: SEO数据包含title和至少5个tags"""
        if not result.success:
            return False
        seo = result.data.get("seo", {})
        has_title = bool(seo.get("seo_title") or seo.get("title"))
        has_tags = len(seo.get("tags", [])) >= 3
        return has_title and has_tags

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
                return json.loads(text[brace_start: brace_end + 1])
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _fallback_seo(title: str, genre: str, analysis: dict) -> dict:
        """当LLM不可用时的降级SEO方案"""
        conflicts = analysis.get("conflicts", [])
        hook = conflicts[0].get("description", "") if conflicts else ""

        tags = [
            "短剧解说", genre, "热门短剧", "剧情解说", "AI解说",
            "短视频", "追剧", "影视解说", "爆款", "高能",
        ]
        characters = analysis.get("characters", [])
        for ch in characters[:3]:
            if ch.get("name"):
                tags.append(ch["name"])

        return {
            "seo_title": f"{title}｜{hook}" if hook else title,
            "description": analysis.get("summary", title),
            "tags": tags,
            "hashtags": [f"#{t}" for t in tags[:8]],
            "thumbnail_text": hook[:6] if hook else title[:6],
            "best_post_time": "周五 20:00",
            "hook_description": hook or title,
        }
