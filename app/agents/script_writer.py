"""
Agent 3: 爆款文案改写Agent（Script Writer）
根据剧情分析结果，生成30-60秒口语化解说文案
融入爆款特征：开头抛冲突、情绪峰值、悬念结尾
"""

from typing import Any, Dict
from loguru import logger

from app.agents.base import BaseAgent, AgentResult
from app.services.llm import _generate_response


SCRIPT_PROMPT = """你是一位百万粉丝的短剧解说博主，擅长写出300万播放量级别的爆款解说文案。

## 剧情分析:
{analysis_json}

## 创作要求:
1. **开头3秒必须炸裂**（用冲突/悬念/反问抓住观众，参考下面的爆款开头公式）
2. 文案时长30-60秒朗读（约200-400字）
3. 全程口语化，像朋友讲故事，语气有起伏
4. 插入"你知道吗""万万没想到""太离谱了"等情绪词
5. 关键冲突点要放慢，制造紧张感
6. 结尾必须有悬念或反转，让人想看原剧
7. 不要出现"字幕""视频""解说"等词
8. 适当用短句和感叹号制造节奏感

## 爆款开头公式（任选其一改编）:
- "一个[身份]的[女人/男人]，竟然当众[做了某事]，全场人都吓傻了……"
- "如果你[身份]突然发现[冲突]，你会怎么办？"
- "千万不要相信[角色]说的话，因为接下来发生的事，没人猜得到……"
- "他用了[数字]年，只为了做一件事——[目标]，结果……"

## 情绪节奏指导:
- 前3句: 🔥 高能开场（冲突/悬念）
- 中间段: 📈 层层递进（每20字要有一个情绪钩子）
- 结尾: 💥 炸裂反转或悬念（观众忍不住要看原片）

请直接输出解说文案，不要加标题、编号或其他说明:
"""


class ScriptWriterAgent(BaseAgent):
    """
    爆款文案改写Agent

    输入: 剧情分析JSON
    输出: 30-60秒解说文案
    """

    def __init__(self, config: dict):
        super().__init__(config, name="ScriptWriter")

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            analysis (dict): PlotAnalyzerAgent输出的剧情分析
            style (str): 风格偏好 (默认"热血", 可选"悬疑/甜宠/搞笑")
            target_length (int): 目标字数 (默认300)
        """
        analysis = input_data.get("analysis", {})
        if not analysis:
            return AgentResult(
                success=False, error="缺少剧情分析数据"
            )

        import json
        analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
        prompt = SCRIPT_PROMPT.format(analysis_json=analysis_json)

        try:
            script = _generate_response(prompt)
            if not script or not script.strip():
                return AgentResult(success=False, error="LLM返回空文案")

            script = script.strip()

            return AgentResult(
                success=True,
                data={
                    "script": script,
                    "char_count": len(script),
                    "estimated_duration_sec": len(script) * 0.15,
                },
            )

        except Exception as e:
            logger.error(f"[ScriptWriter] 文案生成失败: {e}")
            return AgentResult(success=False, error=str(e))

    def verify(self, result: AgentResult) -> bool:
        """验证: 文案长度在100-600字之间"""
        if not result.success:
            return False
        script = result.data.get("script", "")
        char_count = len(script)
        if char_count < 100:
            logger.warning(
                f"[ScriptWriter] 文案太短: {char_count}字"
            )
            return False
        if char_count > 600:
            logger.warning(
                f"[ScriptWriter] 文案太长: {char_count}字，将截断"
            )
            # 超长可以接受，后续截断
        return True
