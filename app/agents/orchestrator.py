"""
多Agent编排器（Orchestrator）v5.0 — 短剧超级操盘手版
协调18个Agent按顺序/并行执行，实现全自动短剧内容生产

v5.0 双模式:
  narration（解说模式）:
    PersonaMaster → TopicEngine → CompetitorDecode → MaterialScout
      → PlotAnalyzer → ScriptWriter → ReviewDiagnosis → VoiceAgent/DubbingAgent
      → BrollMatcher → VideoGen → VideoEditor → VisualAsset → SEO → Publish

  drama（原创短剧模式）:
    PersonaMaster → TopicEngine → ScriptWriter → CharacterGen → StoryboardBreaker
      → DubbingAgent → VideoGen → VideoEditor → VisualAsset → SEO → Publish

  DailyOperator (Supervisor模式，可独立调用)

支持:
  - 双模式：解说 vs 原创短剧（自动/手动切换）
  - 单条视频生产
  - 批量模式（多条素材并行）
  - 操盘手模式（~daily 一键全流程）
  - 竞品拆解 + 公式库自动积累
  - 持久化画像 + 风格一致性
  - 5维度爆款评分诊断
  - 4模式智能选题
  - 进度回调
  - B-roll自动匹配（可选）
  - AI视频生成（可选，Kling/Runway）
  - 角色生成 + 分镜拆解（v5.0）
  - GPT-SoVITS高质克隆配音（v5.0）
  - 视觉卡片/封面生成（v5.0）
  - SEO优化
  - 自动发布（可选）
  - 自我迭代反馈
  - 跨会话记忆持久化（v5.0）
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
# v3.0 Agents
from app.agents.video_gen import VideoGenAgent
from app.agents.broll_matcher import BrollMatcherAgent
from app.agents.seo_agent import SEOAgent
from app.agents.publish_agent import PublishAgent
# v4.0 新增 Agents
from app.agents.persona_master import PersonaMasterAgent
from app.agents.competitor_decode import CompetitorDecodeAgent
from app.agents.topic_engine import TopicEngineAgent
from app.agents.review_diagnosis import ReviewDiagnosisAgent
from app.agents.daily_operator import DailyOperatorAgent
# v5.0 新增 Agents
from app.agents.character_gen import CharacterGenAgent
from app.agents.storyboard_breaker import StoryboardBreakerAgent
from app.agents.dubbing_agent import DubbingAgent
from app.agents.visual_asset import VisualAssetAgent


class AgentOrchestrator:
    """
    全自动多Agent编排器 v5.0 — 短剧超级操盘手版

    双模式:
        narration: 解说模式（YouTube/Reddit短剧解说）
        drama: 原创短剧模式（主题→角色→分镜→生成→合成）

    用法:
        orch = AgentOrchestrator(config)
        # 解说模式 (v3/v4兼容)
        results = orch.run(keywords="short drama revenge")
        # 原创短剧模式 (v5.0新增)
        results = orch.run_drama(theme="复仇短剧 女主被渣男抛弃", episodes=5)
        # 操盘手模式 (v4.0 ~daily)
        plan = orch.run_daily(batch_size=5, topic_mode="hot")
        # 竞品拆解
        decode = orch.run_decode("竞品文案文本...")
        # 选题
        topics = orch.run_topics(mode="hot")
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
        # v3.0
        self.video_gen = VideoGenAgent(config)
        self.broll_matcher = BrollMatcherAgent(config)
        self.seo_agent = SEOAgent(config)
        self.publish_agent = PublishAgent(config)
        # v4.0 新增
        self.persona_master = PersonaMasterAgent(config)
        self.competitor_decode = CompetitorDecodeAgent(config)
        self.topic_engine = TopicEngineAgent(config)
        self.review_diagnosis = ReviewDiagnosisAgent(config)
        self.daily_operator = DailyOperatorAgent(config)
        # v5.0 新增
        self.character_gen = CharacterGenAgent(config)
        self.storyboard_breaker = StoryboardBreakerAgent(config)
        self.dubbing_agent = DubbingAgent(config)
        self.visual_asset = VisualAssetAgent(config)

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

        # ---- Agent v5.0: 视觉资产（封面/卡片） ----
        self._update_progress(
            "VisualAsset", base_pct + 54,
            f"[{idx+1}/{total}] 生成封面/卡片...",
        )
        va_result = self.visual_asset.execute({
            "title": title,
            "script": script,
            "session_id": session_id,
            "styles": ["thumbnail"],
        })
        result["visual_assets"] = va_result.data.get("visual_assets", []) if va_result.success else []

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
    # v4.0: 操盘手模式入口
    # ------------------------------------------------------------------

    def run_daily(
        self,
        batch_size: int = 5,
        topic_mode: str = "hot",
        auto_mode: bool = True,
        user_input: str = "",
    ) -> Dict[str, Any]:
        """
        操盘手模式 (~daily)：一键启动全流程

        Args:
            batch_size: 每日产出数量
            topic_mode: 选题模式 (hot/mine/rival/flash)
            auto_mode: 全自动模式
            user_input: 用户画像输入（首次使用时）
        """
        self._update_progress("DailyOperator", 0, "启动操盘手模式...")

        # Phase 1: 加载/生成画像
        self._update_progress("PersonaMaster", 5, "加载创作者画像...")
        persona_result = self.persona_master.execute({"user_input": user_input})
        persona = persona_result.data.get("persona", {}) if persona_result.success else {}

        # Phase 2: 智能选题
        self._update_progress("TopicEngine", 15, f"生成选题 (模式: {topic_mode})...")
        topics_result = self.topic_engine.execute({
            "mode": topic_mode,
            "persona": persona,
        })
        topics = topics_result.data.get("topics", []) if topics_result.success else []

        # Phase 3: 生成日计划
        self._update_progress("DailyOperator", 30, "生成每日内容计划...")
        daily_result = self.daily_operator.execute({
            "batch_size": batch_size,
            "topic_mode": topic_mode,
            "persona": persona,
            "topics": topics,
            "auto_mode": auto_mode,
        })

        plan = daily_result.data.get("daily_plan", {}) if daily_result.success else {}

        self._update_progress("DailyOperator", 100, "操盘手计划就绪")

        return {
            "success": daily_result.success,
            "persona": persona,
            "topics": topics,
            "daily_plan": plan,
            "plan_path": daily_result.data.get("plan_path", "") if daily_result.success else "",
            "next_steps": daily_result.data.get("next_steps", []) if daily_result.success else [],
        }

    def run_decode(
        self, competitor_text: str, source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        竞品拆解 (~decode)

        Args:
            competitor_text: 竞品文案文本
            source: 来源平台
        """
        self._update_progress("CompetitorDecode", 0, "开始拆解竞品...")
        result = self.competitor_decode.execute({
            "competitor_text": competitor_text,
            "source": source,
        })
        self._update_progress("CompetitorDecode", 100, "拆解完成")
        return {
            "success": result.success,
            "decode": result.data.get("decode", {}) if result.success else {},
            "error": result.error,
        }

    def run_topics(
        self,
        mode: str = "hot",
        context: str = "",
        user_input: str = "",
    ) -> Dict[str, Any]:
        """
        智能选题 (~topics)

        Args:
            mode: 选题模式 (mine/hot/rival/flash)
            context: 附加上下文
            user_input: 用户画像输入
        """
        self._update_progress("TopicEngine", 0, "生成选题...")

        # Load persona
        persona_result = self.persona_master.execute({"user_input": user_input})
        persona = persona_result.data.get("persona", {}) if persona_result.success else {}

        result = self.topic_engine.execute({
            "mode": mode,
            "persona": persona,
            "context": context,
        })

        self._update_progress("TopicEngine", 100, "选题完成")
        return {
            "success": result.success,
            "topics": result.data.get("topics", []) if result.success else [],
            "strategy_note": result.data.get("strategy_note", "") if result.success else "",
            "error": result.error,
        }

    def run_review(
        self, script: str, title: str = "", user_input: str = ""
    ) -> Dict[str, Any]:
        """
        质量诊断 (~review)

        Args:
            script: 待诊断文案
            title: 视频标题
            user_input: 用户画像输入
        """
        self._update_progress("ReviewDiagnosis", 0, "开始质量诊断...")

        persona_result = self.persona_master.execute({"user_input": user_input})
        persona = persona_result.data.get("persona", {}) if persona_result.success else {}

        result = self.review_diagnosis.execute({
            "script": script,
            "title": title,
            "persona": persona,
        })

        self._update_progress("ReviewDiagnosis", 100, "诊断完成")
        return {
            "success": result.success,
            "review": result.data.get("review", {}) if result.success else {},
            "error": result.error,
        }

    # ------------------------------------------------------------------
    # v5.0: 原创短剧模式入口
    # ------------------------------------------------------------------

    def run_drama(
        self,
        theme: str,
        episodes: int = 1,
        user_input: str = "",
    ) -> List[Dict[str, Any]]:
        """
        原创短剧模式 (v5.0) — 从主题到成品视频全链路

        流程: PersonaMaster → ScriptWriter → CharacterGen → StoryboardBreaker
              → DubbingAgent → VideoGen → VideoEditor → VisualAsset → SEO → Publish

        Args:
            theme: 主题描述（如 "复仇短剧 女主被渣男抛弃"）
            episodes: 生成集数（默认1）
            user_input: 用户画像输入
        """
        start = time.time()
        all_results: List[Dict[str, Any]] = []

        # Phase 1: 加载画像
        self._update_progress("PersonaMaster", 0, "加载创作者画像...")
        persona_result = self.persona_master.execute({"user_input": user_input})
        persona = persona_result.data.get("persona", {}) if persona_result.success else {}

        for ep in range(episodes):
            ep_result = self._process_drama_episode(theme, ep, episodes, persona)
            all_results.append(ep_result)

        elapsed = time.time() - start
        success_count = sum(1 for r in all_results if r.get("success"))
        self._update_progress(
            "Orchestrator", 100,
            f"原创短剧完成！成功 {success_count}/{len(all_results)} 集，"
            f"总耗时 {elapsed:.0f}s",
        )

        self._save_iteration_data(all_results)
        self._save_memory({"mode": "drama", "theme": theme, "results": len(all_results)})

        return all_results

    def _process_drama_episode(
        self, theme: str, ep_idx: int, total_eps: int, persona: dict
    ) -> Dict[str, Any]:
        """处理原创短剧单集"""
        session_id = f"drama_{uuid.uuid4().hex[:6]}_ep{ep_idx + 1}"
        base_pct = int((ep_idx / max(total_eps, 1)) * 100)
        result: Dict[str, Any] = {
            "success": False,
            "session_id": session_id,
            "title": f"{theme} (第{ep_idx + 1}集)",
            "mode": "drama",
        }

        # Step 1: 生成剧本
        self._update_progress(
            "ScriptWriter", base_pct + 5,
            f"[{ep_idx+1}/{total_eps}] 创作剧本...",
        )
        script_result = self.script_writer.execute({
            "analysis": {
                "title": theme,
                "summary": theme,
                "genre": "原创短剧",
                "characters": [],
                "conflicts": [{"description": theme, "intensity": "高"}],
                "reversals": [],
                "emotional_peaks": [],
                "hook_points": [],
            },
        })
        if not script_result.success:
            result["error"] = f"剧本生成失败: {script_result.error}"
            result["stage"] = "script_writer"
            return result
        script = script_result.data.get("script", "")
        result["script"] = script

        # Step 2: 角色生成
        self._update_progress(
            "CharacterGen", base_pct + 15,
            f"[{ep_idx+1}/{total_eps}] 生成角色...",
        )
        char_result = self.character_gen.execute({
            "theme": theme,
            "script": script,
        })
        characters = char_result.data.get("characters", []) if char_result.success else []
        result["characters"] = characters

        # Step 3: 分镜拆解
        self._update_progress(
            "StoryboardBreaker", base_pct + 25,
            f"[{ep_idx+1}/{total_eps}] 拆解分镜...",
        )
        sb_result = self.storyboard_breaker.execute({
            "script": script,
            "characters": characters,
        })
        storyboard = sb_result.data.get("storyboard", []) if sb_result.success else []
        result["storyboard"] = storyboard

        # Step 4: 高质配音
        self._update_progress(
            "DubbingAgent", base_pct + 35,
            f"[{ep_idx+1}/{total_eps}] 角色配音...",
        )
        dub_result = self.dubbing_agent.execute({
            "script": script,
            "characters": characters,
            "session_id": session_id,
        })
        dubbed_audio = dub_result.data.get("dubbed_audio", "") if dub_result.success else ""
        result["dubbed_audio"] = dubbed_audio

        # Step 5: AI视频生成
        self._update_progress(
            "VideoGen", base_pct + 45,
            f"[{ep_idx+1}/{total_eps}] AI视频生成...",
        )
        vgen_result = self.video_gen.execute({
            "script": script,
            "session_id": session_id,
            "duration": 60,
        })
        ai_video_clips = vgen_result.data.get("video_clips", []) if vgen_result.success else []

        # Step 6: 视频合成
        self._update_progress(
            "VideoEditor", base_pct + 55,
            f"[{ep_idx+1}/{total_eps}] 合成视频...",
        )
        video_result = self.video_editor.execute({
            "script": script,
            "audio_path": dubbed_audio,
            "durations": [],
            "source_video_path": "",
            "session_id": session_id,
            "title": f"{theme} (第{ep_idx + 1}集)",
            "analysis": {"title": theme, "genre": "原创短剧"},
        })
        if not video_result.success:
            result["error"] = f"视频合成失败: {video_result.error}"
            result["stage"] = "video_editor"
            return result
        video_path = video_result.data.get("video_path", "")
        result["video_path"] = video_path

        # Step 7: 视觉资产（封面/卡片）
        self._update_progress(
            "VisualAsset", base_pct + 65,
            f"[{ep_idx+1}/{total_eps}] 生成封面...",
        )
        va_result = self.visual_asset.execute({
            "title": f"{theme} (第{ep_idx + 1}集)",
            "script": script,
            "session_id": session_id,
            "styles": ["thumbnail", "tiktok_cover"],
        })
        result["visual_assets"] = va_result.data.get("visual_assets", []) if va_result.success else []

        # Step 8: SEO优化
        self._update_progress(
            "SEOAgent", base_pct + 75,
            f"[{ep_idx+1}/{total_eps}] SEO优化...",
        )
        seo_result = self.seo_agent.execute({
            "title": f"{theme} (第{ep_idx + 1}集)",
            "analysis": {"title": theme, "genre": "原创短剧"},
            "script": script,
        })
        seo_data = seo_result.data.get("seo", {}) if seo_result.success else {}
        result["seo"] = seo_data

        # Step 9: 发布
        self._update_progress(
            "PublishAgent", base_pct + 85,
            f"[{ep_idx+1}/{total_eps}] 准备发布...",
        )
        pub_result = self.publish_agent.execute({
            "video_path": video_path,
            "seo": seo_data,
            "session_id": session_id,
        })
        if pub_result.success:
            result["publish"] = pub_result.data

        result["success"] = True
        result["ai_video_clips"] = ai_video_clips

        self._update_progress(
            "Orchestrator", base_pct + 95,
            f"[{ep_idx+1}/{total_eps}] ✅ 原创短剧完成!",
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

    # ------------------------------------------------------------------
    # v5.0: 跨会话记忆持久化
    # ------------------------------------------------------------------

    def _save_memory(self, session_data: Dict[str, Any]):
        """保存跨会话记忆数据（Toonflow记忆层）"""
        memory_path = Path(self.config.get("app", {}).get("root_dir", ".")) / "config" / "memory.json"
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载已有记忆
        memories: List[Dict] = []
        if memory_path.exists():
            try:
                with open(str(memory_path), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    memories = data.get("sessions", [])
            except (json.JSONDecodeError, KeyError):
                memories = []

        # 追加新记忆（保留最近100条）
        memories.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            **session_data,
        })
        memories = memories[-100:]

        with open(str(memory_path), "w", encoding="utf-8") as f:
            json.dump({"sessions": memories}, f, ensure_ascii=False, indent=2)
        logger.info(f"[Orchestrator] 记忆已更新: {memory_path}")
