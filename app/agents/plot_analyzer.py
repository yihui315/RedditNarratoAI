"""
Agent 2: 剧情提取 & 冲突分析Agent（Plot Analyzer）
将字幕/视频描述丢给LLM，提取核心剧情、人物关系、冲突点和反转
输出结构化JSON，便于下游Agent调用
"""

import json
from typing import Any, Dict
from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import generate_response_from_config


PLOT_ANALYSIS_PROMPT = """你是一位专业的短剧剧情分析师。请仔细阅读下面的字幕/文本内容，提取关键信息。

## 字幕/内容:
{subtitle_text}

## 视频标题:
{title}

## 要求
请用JSON格式输出以下内容（不要输出markdown代码块标记，直接输出JSON）:
{{
    "title": "剧名或标题",
    "genre": "类型（如复仇、甜宠、逆袭、悬疑等）",
    "summary": "100字以内的剧情摘要",
    "characters": [
        {{"name": "角色名", "role": "主角/反派/配角", "description": "一句话描述"}}
    ],
    "conflicts": [
        {{"description": "冲突描述", "intensity": "高/中/低"}}
    ],
    "reversals": [
        "反转1描述",
        "反转2描述"
    ],
    "emotional_peaks": [
        {{"moment": "描述", "emotion": "愤怒/感动/震惊/紧张等"}}
    ],
    "hook_points": [
        "适合做开头钩子的情节点1",
        "适合做开头钩子的情节点2"
    ]
}}
"""


_WEBVTT_HEADER = "WEBVTT"


class PlotAnalyzerAgent(BaseAgent):
    """
    剧情提取Agent

    输入: 字幕文本 + 视频标题
    输出: 结构化剧情分析JSON
    """

    def __init__(self, config: dict):
        super().__init__(config, name="PlotAnalyzer")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            subtitle_text (str): 字幕全文
            title (str): 视频标题
            subtitle_path (str): 字幕文件路径（如果subtitle_text为空则读取文件）
        """
        subtitle_text = input_data.get("subtitle_text", "")
        title = input_data.get("title", "未知")

        # 如果没有直接文本，尝试从文件读取
        if not subtitle_text:
            subtitle_path = input_data.get("subtitle_path", "")
            if subtitle_path:
                subtitle_text = self._read_subtitle_file(subtitle_path)

        if not subtitle_text:
            return AgentResult(
                success=False,
                error="没有可分析的字幕文本",
            )

        # 截取前8000字符避免超token限制
        subtitle_text = subtitle_text[:8000]

        prompt = PLOT_ANALYSIS_PROMPT.format(
            subtitle_text=subtitle_text,
            title=title,
        )

        try:
            raw_response = generate_response_from_config(prompt, self.config)
            if not raw_response:
                return AgentResult(success=False, error="LLM返回空响应")

            analysis = self._parse_json_response(raw_response)
            if not analysis:
                return AgentResult(
                    success=False,
                    error="LLM响应无法解析为JSON",
                    data={"raw_response": raw_response},
                )

            return AgentResult(
                success=True,
                data={
                    "analysis": analysis,
                    "title": title,
                    "raw_response": raw_response,
                },
            )

        except Exception as e:
            logger.error(f"[PlotAnalyzer] LLM调用失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: JSON必须包含summary和至少1个conflict"""
        if not result.success:
            return False
        analysis = result.data.get("analysis", {})
        has_summary = bool(analysis.get("summary"))
        has_conflicts = len(analysis.get("conflicts", [])) > 0
        return has_summary and has_conflicts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_subtitle_file(path: str) -> str:
        """读取SRT/VTT字幕文件为纯文本"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            text_lines = []
            for line in lines:
                line = line.strip()
                # 跳过序号、时间戳和空行
                if not line:
                    continue
                if line.isdigit():
                    continue
                if "-->" in line:
                    continue
                if line.startswith(_WEBVTT_HEADER):
                    continue
                text_lines.append(line)

            return "\n".join(text_lines)
        except Exception as e:
            logger.error(f"读取字幕文件失败: {e}")
            return ""

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """从LLM响应中提取JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取```json ... ```块
        import re
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个{...}块
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        return {}
