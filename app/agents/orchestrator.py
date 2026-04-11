"""
多Agent编排器（Orchestrator）
协调5个Agent按顺序/并行执行，实现全自动短剧解说视频生产

工作流:
  MaterialScout → PlotAnalyzer → ScriptWriter → VoiceAgent → VideoEditor

支持:
  - 单条视频生产
  - 批量模式（多条素材并行）
  - 进度回调
"""

import uuid
import time
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import AgentResult
from app.agents.material_scout import MaterialScoutAgent
from app.agents.plot_analyzer import PlotAnalyzerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.video_editor import VideoEditorAgent


class AgentOrchestrator:
    """
    全自动多Agent编排器

    用法:
        orch = AgentOrchestrator(config)
        results = orch.run(keywords="short drama revenge")
        # 或
        results = orch.run(urls=["https://youtube.com/watch?v=xxx"])
    """

    def __init__(self, config: dict):
        self.config = config
        self._progress_callback: Optional[Callable[[str, int, str], None]] = None

        # 初始化所有Agent
        self.material_scout = MaterialScoutAgent(config)
        self.plot_analyzer = PlotAnalyzerAgent(config)
        self.script_writer = ScriptWriterAgent(config)
        self.voice_agent = VoiceAgent(config)
        self.video_editor = VideoEditorAgent(config)

    def set_progress_callback(
        self, callback: Callable[[str, int, str], None]
    ):
        """设置进度回调 callback(agent_name, percent, message)"""
        self._progress_callback = callback

    def _update_progress(self, agent: str, percent: int, msg: str):
        logger.info(f"[Orchestrator][{agent}][{percent}%] {msg}")
        if self._progress_callback:
            self._progress_callback(agent, percent, msg)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def run(
        self,
        keywords: str = "",
        urls: Optional[List[str]] = None,
        max_videos: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        运行完整的多Agent流水线

        Args:
            keywords: YouTube搜索关键词
            urls: 直接指定视频URL列表
            max_videos: 最多处理几条视频

        Returns:
            list[dict]: 每条视频的完整生产结果
        """
        start = time.time()
        all_results: List[Dict[str, Any]] = []

        # ---- Step 1: 素材识别 ----
        self._update_progress("MaterialScout", 0, "开始搜索素材...")
        scout_result = self.material_scout.execute({
            "keywords": keywords,
            "urls": urls or [],
            "max_results": max_videos,
        })

        if not scout_result.success:
            logger.error(f"素材识别失败: {scout_result.error}")
            return [{
                "success": False,
                "stage": "material_scout",
                "error": scout_result.error,
            }]

        materials = scout_result.data.get("materials", [])
        self._update_progress(
            "MaterialScout", 20,
            f"找到 {len(materials)} 条素材",
        )

        # ---- Step 2-5: 对每条素材执行完整流水线 ----
        for idx, material in enumerate(materials):
            video_result = self._process_single_material(
                material, idx, len(materials)
            )
            all_results.append(video_result)

        elapsed = time.time() - start
        success_count = sum(1 for r in all_results if r.get("success"))
        self._update_progress(
            "Orchestrator", 100,
            f"完成！成功 {success_count}/{len(all_results)} 条，"
            f"总耗时 {elapsed:.0f}s",
        )

        return all_results

    # ------------------------------------------------------------------
    # Single material pipeline
    # ------------------------------------------------------------------

    def _process_single_material(
        self, material: dict, idx: int, total: int
    ) -> Dict[str, Any]:
        """对单条素材执行完整Agent链"""
        session_id = f"{material.get('video_id', 'vid')}_{uuid.uuid4().hex[:4]}"
        title = material.get("title", "未知短剧")
        base_pct = int(20 + (idx / max(total, 1)) * 80)

        result: Dict[str, Any] = {
            "success": False,
            "session_id": session_id,
            "title": title,
            "material": material,
        }

        # ---- Agent 2: 剧情提取 ----
        self._update_progress(
            "PlotAnalyzer", base_pct,
            f"[{idx+1}/{total}] 分析剧情: {title}",
        )
        plot_result = self.plot_analyzer.execute({
            "subtitle_path": material.get("subtitle_path", ""),
            "title": title,
        })
        if not plot_result.success:
            result["error"] = f"剧情分析失败: {plot_result.error}"
            result["stage"] = "plot_analyzer"
            return result

        analysis = plot_result.data.get("analysis", {})
        result["analysis"] = analysis

        # ---- Agent 3: 文案改写 ----
        self._update_progress(
            "ScriptWriter", base_pct + 15,
            f"[{idx+1}/{total}] 生成文案...",
        )
        script_result = self.script_writer.execute({
            "analysis": analysis,
        })
        if not script_result.success:
            result["error"] = f"文案生成失败: {script_result.error}"
            result["stage"] = "script_writer"
            return result

        script = script_result.data.get("script", "")
        result["script"] = script

        # ---- Agent 4: 配音 ----
        self._update_progress(
            "VoiceAgent", base_pct + 30,
            f"[{idx+1}/{total}] 生成配音...",
        )
        voice_result = self.voice_agent.execute({
            "script": script,
            "session_id": session_id,
        })
        if not voice_result.success:
            result["error"] = f"配音失败: {voice_result.error}"
            result["stage"] = "voice_agent"
            return result

        result["audio_path"] = voice_result.data.get("audio_path", "")

        # ---- Agent 5: 视频剪辑 ----
        self._update_progress(
            "VideoEditor", base_pct + 50,
            f"[{idx+1}/{total}] 合成视频...",
        )
        video_result = self.video_editor.execute({
            "script": script,
            "audio_path": voice_result.data.get("audio_path", ""),
            "durations": voice_result.data.get("durations", []),
            "source_video_path": material.get("video_path", ""),
            "session_id": session_id,
            "title": title,
            "analysis": analysis,
        })
        if not video_result.success:
            result["error"] = f"视频合成失败: {video_result.error}"
            result["stage"] = "video_editor"
            return result

        result["success"] = True
        result["video_path"] = video_result.data.get("video_path", "")
        result["metadata"] = video_result.data.get("metadata", {})

        self._update_progress(
            "VideoEditor", base_pct + 60,
            f"[{idx+1}/{total}] ✅ 完成: {title}",
        )
        return result
