"""
短剧解说视频全自动Agent系统
5个Agent协作：素材识别 → 剧情提取 → 文案改写 → 配音 → 剪辑输出
"""

from app.agents.base import BaseAgent, AgentResult
from app.agents.material_scout import MaterialScoutAgent
from app.agents.plot_analyzer import PlotAnalyzerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.video_editor import VideoEditorAgent
from app.agents.orchestrator import AgentOrchestrator

__all__ = [
    "BaseAgent",
    "AgentResult",
    "MaterialScoutAgent",
    "PlotAnalyzerAgent",
    "ScriptWriterAgent",
    "VoiceAgent",
    "VideoEditorAgent",
    "AgentOrchestrator",
]
