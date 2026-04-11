"""
多Agent编排器（Orchestrator）v3.0
协调9个Agent按顺序/并行执行，实现全自动短剧解说视频生产

工作流 (v3.0 9-Agent Pipeline):
  MaterialScout → PlotAnalyzer → ScriptWriter → VoiceAgent
    → BrollMatcher → VideoGen → VideoEditor → SEO → Publish

支持:
  - 单条视频生产
  - 批量模式（多条素材并行）
  - 进度回调
  - B-roll自动匹配（可选）
  - AI视频生成（可选，Kling/Runway）
  - SEO优化
  - 自动发布（可选）
  - 自我迭代反馈
"""

import uuid
import json
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
# v3.0 新增 Agents
from app.agents.video_gen import VideoGenAgent
from app.agents.broll_matcher import BrollMatcherAgent
from app.agents.seo_agent import SEOAgent
from app.agents.publish_agent import PublishAgent


class AgentOrchestrator:
    """
    全自动多Agent编排器 v3.0

    用法:
        orch = AgentOrchestrator(config)
        results = orch.run(keywords="short drama revenge")
        # 或
        results = orch.run(urls=["https://youtube.com/watch?v=xxx"])
    """

    def __init__(self, config: dict):
        self.config = config
        self._progress_callback: Optional[Callable[[str, int, str], None]] = None

        # 初始化所有Agent (v3.0: 9 Agents)
        self.material_scout = MaterialScoutAgent(config)
        self.plot_analyzer = PlotAnalyzerAgent(config)
        self.script_writer = ScriptWriterAgent(config)
        self.voice_agent = VoiceAgent(config)
        self.video_editor = VideoEditorAgent(config)
        # v3.0 新增
        self.video_gen = VideoGenAgent(config)
        self.broll_matcher = BrollMatcherAgent(config)
        self.seo_agent = SEOAgent(config)
        self.publish_agent = PublishAgent(config)

        # 自我迭代数据存储
        self._iteration_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "iterations"
        self._iteration_dir.mkdir(parents=True, exist_ok=True)

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
            "MaterialScout", 10,
            f"找到 {len(materials)} 条素材",
        )

        # ---- Step 2-9: 对每条素材执行完整9-Agent流水线 ----
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

        # Save iteration data for self-improvement
        self._save_iteration_data(all_results)

        return all_results

    # ------------------------------------------------------------------
    # Single material pipeline (v3.0: 9 agents)
    # ------------------------------------------------------------------

    def _process_single_material(
        self, material: dict, idx: int, total: int
    ) -> Dict[str, Any]:
        """对单条素材执行完整9-Agent链"""
        session_id = f"{material.get('video_id', 'vid')}_{uuid.uuid4().hex[:4]}"
        title = material.get("title", "未知短剧")
        base_pct = int(10 + (idx / max(total, 1)) * 90)

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
            "ScriptWriter", base_pct + 8,
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
            "VoiceAgent", base_pct + 16,
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

        # ---- Agent 7: B-roll匹配（可选，非阻塞） ----
        self._update_progress(
            "BrollMatcher", base_pct + 24,
            f"[{idx+1}/{total}] 匹配B-roll素材...",
        )
        broll_result = self.broll_matcher.execute({
            "script": script,
            "analysis": analysis,
            "session_id": session_id,
        })
        broll_clips = []
        if broll_result.success:
            broll_clips = broll_result.data.get("broll_clips", [])

        # ---- Agent 6: AI视频生成（可选） ----
        self._update_progress(
            "VideoGen", base_pct + 32,
            f"[{idx+1}/{total}] AI视频生成...",
        )
        vgen_result = self.video_gen.execute({
            "script": script,
            "session_id": session_id,
            "duration": int(voice_result.data.get("total_duration", 60)),
        })
        ai_video_clips = []
        if vgen_result.success:
            ai_video_clips = vgen_result.data.get("video_clips", [])

        # ---- Agent 5: 视频剪辑 ----
        self._update_progress(
            "VideoEditor", base_pct + 40,
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

        video_path = video_result.data.get("video_path", "")
        result["video_path"] = video_path

        # ---- Agent 8: SEO优化 ----
        self._update_progress(
            "SEOAgent", base_pct + 50,
            f"[{idx+1}/{total}] SEO优化...",
        )
        seo_result = self.seo_agent.execute({
            "title": title,
            "analysis": analysis,
            "script": script,
        })
        seo_data = {}
        if seo_result.success:
            seo_data = seo_result.data.get("seo", {})
        result["seo"] = seo_data
        result["metadata"] = seo_data or video_result.data.get("metadata", {})

        # ---- Agent 9: 发布 ----
        self._update_progress(
            "PublishAgent", base_pct + 58,
            f"[{idx+1}/{total}] 准备发布...",
        )
        publish_result = self.publish_agent.execute({
            "video_path": video_path,
            "seo": seo_data,
            "session_id": session_id,
        })
        if publish_result.success:
            result["publish"] = publish_result.data

        result["success"] = True
        result["broll_clips"] = broll_clips
        result["ai_video_clips"] = ai_video_clips

        self._update_progress(
            "Orchestrator", base_pct + 65,
            f"[{idx+1}/{total}] ✅ 完成: {title}",
        )
        return result

    # ------------------------------------------------------------------
    # Self-iteration feedback
    # ------------------------------------------------------------------

    def _save_iteration_data(self, results: List[Dict[str, Any]]):
        """保存迭代数据，供24h后自动反馈优化"""
        iteration_file = self._iteration_dir / f"iteration_{int(time.time())}.json"
        data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_videos": len(results),
            "success_count": sum(1 for r in results if r.get("success")),
            "sessions": [
                {
                    "session_id": r.get("session_id", ""),
                    "title": r.get("title", ""),
                    "success": r.get("success", False),
                    "video_path": r.get("video_path", ""),
                    "seo": r.get("seo", {}),
                    "error": r.get("error", ""),
                }
                for r in results
            ],
        }
        with open(str(iteration_file), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[Orchestrator] 迭代数据已保存: {iteration_file}")
