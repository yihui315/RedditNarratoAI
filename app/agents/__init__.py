"""
短剧解说视频全自动Agent系统 v4.0
14个Agent协作：画像 → 选题 → 竞品拆解 → 素材识别 → 剧情提取 → 文案改写
  → 质量诊断 → 配音 → B-roll匹配 → AI视频生成 → 剪辑输出 → SEO → 发布
  + DailyOperator 操盘手Supervisor
"""

from app.agents.base import BaseAgent, AgentResult
from app.agents.material_scout import MaterialScoutAgent
from app.agents.plot_analyzer import PlotAnalyzerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.video_editor import VideoEditorAgent
from app.agents.orchestrator import AgentOrchestrator
# v3.0
from app.agents.video_gen import VideoGenAgent
from app.agents.broll_matcher import BrollMatcherAgent
from app.agents.seo_agent import SEOAgent
from app.agents.publish_agent import PublishAgent
# v4.0
from app.agents.persona_master import PersonaMasterAgent
from app.agents.competitor_decode import CompetitorDecodeAgent
from app.agents.topic_engine import TopicEngineAgent
from app.agents.review_diagnosis import ReviewDiagnosisAgent
from app.agents.daily_operator import DailyOperatorAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "MaterialScoutAgent",
    "PlotAnalyzerAgent",
    "ScriptWriterAgent",
    "VoiceAgent",
    "VideoEditorAgent",
    "AgentOrchestrator",
    # v3.0
    "VideoGenAgent",
    "BrollMatcherAgent",
    "SEOAgent",
    "PublishAgent",
    # v4.0
    "PersonaMasterAgent",
    "CompetitorDecodeAgent",
    "TopicEngineAgent",
    "ReviewDiagnosisAgent",
    "DailyOperatorAgent",
]
