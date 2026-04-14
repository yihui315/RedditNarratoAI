"""
MovieNarrationPipeline - 电影自动浓缩解说主流水线
=====================================================
遵循 Prompt Chaining 原则：6个Stage顺序执行，每步可单独重试/替换/A-B测试

执行流程：
  transcribe (WhisperX)        → transcript.json
       ↓
  segment   (PySceneDetect)   → scenes.json
       ↓
  chapter   (MiniMax 2.7)      → chapters.json
       ↓
  outline   (MiniMax 2.7)      → outline.json
       ↓
  script    (MiniMax 2.7)      → script_part{1,2,3}.json
       ↓
  reflection(MiniMax 2.7)      → final_script_part{1,2,3}.json
       ↓
  scene_prompts(MiniMax 2.7)  → scene_prompts_part{1,2,3}.json
       ↓
  render_manifest            → render_manifest.json
       ↓
  TTS + 字幕 + FFmpeg渲染    → 3段视频

支持断点续跑：每个Stage完成后写done标记，跳过已完成的Stage
"""

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

DEFAULT_WORK_DIR = "./work/movie"
DEFAULT_STYLE = "悬疑反转"  # 默认风格


# ── 风格预设（Role-Playing + Few-Shot） ─────────────────────────────────────
STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "强狗血": {
        "identity": "你是一名有10年经验的狗血剧情短视频编剧，擅长夸大冲突、强化情绪、制造离奇反转。",
        "tone": "情绪激动、节奏极快、句式短促、口语化",
        "hook_pattern": "开头: 惊人宣言或罕见画面 → 中段: 不断叠加冲突 → 结尾: 反转或悬念",
        "cta": "看到最后你绝对想不到",
        "examples": [
            {
                "type": "input",
                "text": "女主发现男友出轨，却发现男友是她失散多年的亲哥哥...",
            },
            {
                "type": "output",
                "text": "就在她准备求婚的当天，一个匿名包裹彻底改变了一切。里面是一张照片——她男友，和一个和她长得一模一样的女人，站在一起。等等，她不是独生女吗？这件事，远比她想象的更恐怖...",
            },
        ],
    },
    "悬疑反转": {
        "identity": "你是一名有10年经验的悬疑电影解说编剧，擅长层层铺垫、误导观众、结尾反转。",
        "tone": "冷静克制、信息密度高、悬念递进、逻辑严密",
        "hook_pattern": "开头: 抛出一个谜题或异常事件 → 中段: 不断给出误导线索 → 结尾: 反转揭示真相",
        "cta": "这个结局，90%的人都没猜到",
        "examples": [
            {
                "type": "input",
                "text": "一个男人醒来发现自己被困在一个白色房间里，墙上有一个洞...",
            },
            {
                "type": "output",
                "text": "他醒来时躺在一个纯白的房间里。墙上有个洞，大小刚好能伸进一只手。他完全不记得自己是怎么来到这里的。但他注意到一个细节——那个洞的边缘，有血迹...",
            },
        ],
    },
    "爽文逆袭": {
        "identity": "你是一名有10年经验的逆袭爽文短视频编剧，擅长先抑后扬、碾压对手、情绪释放。",
        "tone": "前半段压抑委屈 → 后半段爆发碾压，情绪从低到极高",
        "hook_pattern": "开头: 主角被踩到最低点 → 中段: 隐忍积蓄 → 结尾: 逆天反杀",
        "cta": "从被踩到万人捧，他只用了这一部电影的时间",
        "examples": [
            {
                "type": "input",
                "text": "一个被所有人看不起的底层员工，实际上是隐藏身份的商业帝王...",
            },
            {
                "type": "output",
                "text": "在公司里，他是最不起眼的那个人。同事欺负他，老板看不起他，连保安都对他冷嘲热讽。但没人知道，他的另一个身份——让这座城市最顶层的人物，见了他都要恭敬三分...",
            },
        ],
    },
}


@dataclass
class StageResult:
    """单步执行结果"""
    success: bool
    output_path: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    stage: str = ""


@dataclass
class PipelineConfig:
    """流水线配置"""
    # MiniMax 2.7 (OpenAI-compatible)
    api_base: str = "https://api.minimax.chat/v1"
    api_key: str = ""
    model: str = "MiniMax-2.7-T2I"

    # 本地工具
    whisperx_model: str = "base"
    scene_threshold: float = 30.0  # PySceneDetect 阈值

    # 输出
    work_dir: str = DEFAULT_WORK_DIR
    output_dir: str = "./output/movie"

    # 风格
    style: str = DEFAULT_STYLE
    target_lang: str = "zh"

    # 视频参数
    num_parts: int = 3
    target_duration_per_part_sec: int = 300  # 5分钟

    # 调试
    skip_transcribe: bool = False  # 跳过转写（已有transcript.json）
    skip_segment: bool = False
    skip_chapter: bool = False
    skip_outline: bool = False
    skip_script: bool = False
    skip_reflection: bool = False
    skip_scene_prompts: bool = False
    force_reflection: bool = False  # 强制Reflection即使模型自评够高

    def style_preset(self) -> Dict[str, Any]:
        return STYLE_PRESETS.get(self.style, STYLE_PRESETS["悬疑反转"])


class MovieNarrationPipeline:
    """
    电影自动浓缩解说流水线
    支持断点续跑：每个Stage完成后写 .done 文件
    """

    def __init__(self, config: PipelineConfig = None):
        self.cfg = config or PipelineConfig()
        self.session_id = uuid.uuid4().hex[:8]
        self.work_dir = Path(self.cfg.work_dir) / f"session_{self.session_id}"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, cb: Callable[[str, int], None]):
        self._progress_callback = cb

    def _update(self, msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")
        if self._progress_callback:
            self._progress_callback(msg, pct)

    # ── 公共入口 ─────────────────────────────────────────────────────────────

    def run(
        self,
        video_path: str,
        transcript_path: str = None,
        scenes_path: str = None,
    ) -> Dict[str, Any]:
        """
        执行完整流水线

        Args:
            video_path: 电影视频文件路径
            transcript_path: 可选，已有转写文件
            scenes_path: 可选，已有镜头分段文件

        Returns:
            {success, work_dir, render_manifest, error, stages}
        """
        if not os.path.exists(video_path):
            return {"success": False, "error": f"Video not found: {video_path}"}

        stages = {}

        # ── Stage 1: 转写 ──────────────────────────────────────────────────
        if transcript_path and os.path.exists(transcript_path):
            self._update("使用已有的transcript.json", 5)
            t_path = transcript_path
        elif self.cfg.skip_transcribe:
            t_path = str(self.work_dir / "transcript.json")
            if not os.path.exists(t_path):
                return {"success": False, "error": "skip_transcribe=True but no transcript found"}
        else:
            r = self._stage_transcribe(video_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            t_path = r.output_path
        stages["transcribe"] = {"success": True, "path": t_path}

        # ── Stage 2: 镜头切分 ──────────────────────────────────────────────
        if scenes_path and os.path.exists(scenes_path):
            self._update("使用已有的scenes.json", 15)
            s_path = scenes_path
        elif self.cfg.skip_segment:
            s_path = str(self.work_dir / "scenes.json")
            if not os.path.exists(s_path):
                return {"success": False, "error": "skip_segment=True but no scenes found"}
        else:
            r = self._stage_segment(video_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            s_path = r.output_path
        stages["segment"] = {"success": True, "path": s_path}

        # ── Stage 3: 章节摘要 ──────────────────────────────────────────────
        c_path = str(self.work_dir / "chapters.json")
        if os.path.exists(c_path + ".done"):
            self._update("跳过已完成: chapter", 20)
        else:
            r = self._stage_chapter(t_path, s_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            c_path = r.output_path
            Path(c_path + ".done").touch()
        stages["chapter"] = {"success": True, "path": c_path}

        # ── Stage 4: 三段式大纲 ───────────────────────────────────────────
        o_path = str(self.work_dir / "outline.json")
        if os.path.exists(o_path + ".done"):
            self._update("跳过已完成: outline", 30)
        else:
            r = self._stage_outline(c_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            o_path = r.output_path
            Path(o_path + ".done").touch()
        stages["outline"] = {"success": True, "path": o_path}

        # ── Stage 5: 详细脚本 ─────────────────────────────────────────────
        script_dir = self.work_dir / "scripts"
        script_dir.mkdir(exist_ok=True)
        script_paths = []
        for i in range(1, self.cfg.num_parts + 1):
            sp = script_dir / f"script_part{i}.json"
            if sp.exists() and not self.cfg.skip_script:
                self._update(f"跳过已完成: script_part{i}", 40 + i * 5)
                script_paths.append(str(sp))
                continue
            r = self._stage_script(o_path, part_num=i)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            script_paths.append(r.output_path)
        stages["script"] = {"success": True, "paths": script_paths}

        # ── Stage 6: Reflection自检 ────────────────────────────────────────
        final_script_dir = self.work_dir / "final_scripts"
        final_script_dir.mkdir(exist_ok=True)
        final_paths = []
        for i, sp in enumerate(script_paths):
            fp = final_script_dir / f"final_script_part{i+1}.json"
            need_reflect = (
                not fp.exists()
                or self.cfg.force_reflection
            )
            if not need_reflect:
                self._update(f"跳过已完成: reflection_part{i+1}", 55 + i * 5)
                final_paths.append(str(fp))
                continue
            r = self._stage_reflection(sp)
            if not r.success:
                # Reflection失败不影响主流程，用原脚本
                logger.warning(f"Reflection failed for part{i+1}, using original")
                shutil.copy2(sp, fp)
            else:
                shutil.copy2(r.output_path, fp)
            final_paths.append(str(fp))
            Path(str(fp) + ".done").touch()
        stages["reflection"] = {"success": True, "paths": final_paths}

        # ── Stage 7: LLM-as-Judge评分 ──────────────────────────────────────
        j_path = str(self.work_dir / "judge_scores.json")
        if not os.path.exists(j_path + ".done"):
            r = self._stage_judge(final_paths)
            if r.success:
                shutil.copy2(r.output_path, j_path)
                Path(j_path + ".done").touch()
            else:
                logger.warning(f"Judge failed: {r.error}")
        stages["judge"] = {"success": True, "path": j_path}

        # ── Stage 8: 镜头提示生成 ─────────────────────────────────────────
        prompt_dir = self.work_dir / "scene_prompts"
        prompt_dir.mkdir(exist_ok=True)
        prompt_paths = []
        for i, fp in enumerate(final_paths):
            pp = prompt_dir / f"scene_prompts_part{i+1}.json"
            if pp.exists() and not self.cfg.skip_scene_prompts:
                self._update(f"跳过已完成: scene_prompts_part{i+1}", 75 + i * 5)
                prompt_paths.append(str(pp))
                continue
            r = self._stage_scene_prompts(fp, s_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            prompt_paths.append(r.output_path)
        stages["scene_prompts"] = {"success": True, "paths": prompt_paths}

        # ── Stage 9: 渲染清单 ─────────────────────────────────────────────
        rm_path = str(self.work_dir / "render_manifest.json")
        if not os.path.exists(rm_path + ".done"):
            r = self._stage_render_manifest(final_paths, prompt_paths, scenes_path=s_path)
            if not r.success:
                return {"success": False, "error": r.error, "stages": stages}
            rm_path = r.output_path
            Path(rm_path + ".done").touch()
        stages["render_manifest"] = {"success": True, "path": rm_path}

        self._update("流水线执行完成", 100)

        return {
            "success": True,
            "work_dir": str(self.work_dir),
            "render_manifest": rm_path,
            "stages": stages,
            "session_id": self.session_id,
        }

    # ── Stage 1: 转写 ────────────────────────────────────────────────────────

    def _stage_transcribe(self, video_path: str) -> StageResult:
        """WhisperX 转写"""
        self._update("正在转写视频（WhisperX）...", 5)
        output = self.work_dir / "transcript.json"
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(
                self.cfg.whisperx_model,
                device="cpu",
                compute_type="int8",
            )
            segments, info = model.transcribe(
                video_path,
                language="zh",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            result = []
            for seg in segments:
                result.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                })
            total_duration = info.duration or 0
            with open(output, "w", encoding="utf-8") as f:
                json.dump({
                    "transcript": result,
                    "total_duration": total_duration,
                    "language": info.language,
                }, f, ensure_ascii=False, indent=2)
            self._update(f"转写完成，共 {len(result)} 句，片长 {total_duration:.0f}秒", 12)
            return StageResult(success=True, output_path=str(output), stage="transcribe")
        except ImportError:
            # Fallback: 用 FFmpeg + 外部 whisper
            return self._stage_transcribe_ffmpeg(video_path, output)
        except Exception as e:
            logger.exception("[transcribe] Error")
            return StageResult(success=False, error=f"转写失败: {e}", stage="transcribe")

    def _stage_transcribe_ffmpeg(self, video_path: str, output: Path) -> StageResult:
        """FFmpeg fallback: 仅提取音频，供外部 whisper 使用"""
        self._update("WhisperX未安装，使用FFmpeg提取音频...", 5)
        audio_path = str(self.work_dir / "audio.wav")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                audio_path,
            ], capture_output=True, timeout=600)
            if not os.path.exists(audio_path):
                return StageResult(success=False, error="FFmpeg音频提取失败", stage="transcribe")
            # 写一个placeholder，等用户自己用whisper处理
            with open(output, "w", encoding="utf-8") as f:
                json.dump({
                    "audio_path": audio_path,
                    "note": "请用 whisper CLI 或 faster-whisper 处理此音频",
                    "transcript": [],
                }, f)
            return StageResult(success=True, output_path=str(output), stage="transcribe")
        except Exception as e:
            return StageResult(success=False, error=str(e), stage="transcribe")

    # ── Stage 2: 镜头切分 ────────────────────────────────────────────────────

    def _stage_segment(self, video_path: str) -> StageResult:
        """PySceneDetect 镜头切分"""
        self._update("正在检测镜头切分（PySceneDetect）...", 15)
        output = self.work_dir / "scenes.json"
        try:
            from scenedetect import SceneManager, VideoManager
            from scenedetect.detectors import ContentDetector
            # scenedetect 0.6.x API: VideoManager 接收路径列表
            video_mgr = VideoManager([video_path])
            sm = SceneManager()
            sm.add_detector(ContentDetector(threshold=self.cfg.scene_threshold))
            video_mgr.start()
            sm.detect_scenes(video_mgr)
            scenes = sm.get_scene_list()
            result = []
            for i, scene in enumerate(scenes):
                result.append({
                    "id": i,
                    "start_sec": round(scene[0].get_seconds(), 2),
                    "end_sec": round(scene[1].get_seconds(), 2),
                    "duration_sec": round((scene[1] - scene[0]).get_seconds(), 2),
                })
            video_mgr.release()
            with open(output, "w", encoding="utf-8") as f:
                json.dump({"scenes": result}, f, ensure_ascii=False, indent=2)
            self._update(f"镜头检测完成，共 {len(result)} 个镜头", 18)
            return StageResult(success=True, output_path=str(output), stage="segment")
        except ImportError:
            # Fallback: 用 FFmpeg scene detection
            return self._stage_segment_ffmpeg(video_path, output)
        except Exception as e:
            logger.exception("[segment] Error")
            return StageResult(success=False, error=f"镜头检测失败: {e}", stage="segment")

    def _stage_segment_ffmpeg(self, video_path: str, output: Path) -> StageResult:
        """FFmpeg scene detection fallback"""
        import re
        self._update("PySceneDetect未安装，使用FFmpeg scene detection...", 15)
        try:
            result = subprocess.run([
                "ffmpeg", "-i", video_path,
                "-filter:v", "select='gt(scene,0.3)',showinfo",
                "-f", "null", "-",
            ], capture_output=True, text=True, timeout=300)
            # 解析时间戳
            matches = re.findall(r"pts_time:([\d.]+)", result.stderr + result.stdout)
            timestamps = sorted(set(float(m) for m in matches[:100]))  # 最多100个切分点
            scenes = []
            for i in range(len(timestamps) - 1):
                scenes.append({
                    "id": i,
                    "start_sec": round(timestamps[i], 2),
                    "end_sec": round(timestamps[i + 1], 2),
                    "duration_sec": round(timestamps[i + 1] - timestamps[i], 2),
                })
            with open(output, "w", encoding="utf-8") as f:
                json.dump({"scenes": scenes}, f)
            return StageResult(success=True, output_path=str(output), stage="segment")
        except Exception as e:
            return StageResult(success=False, error=str(e), stage="segment")

    # ── Stage 3: 章节摘要 ────────────────────────────────────────────────────

    def _stage_chapter(self, transcript_path: str, scenes_path: str) -> StageResult:
        """MiniMax 2.7: 转写文本 + 镜头信息 → 章节摘要"""
        self._update("正在生成章节摘要（MiniMax 2.7）...", 20)
        output = self.work_dir / "chapters.json"

        with open(transcript_path, encoding="utf-8") as f:
            transcript_data = json.load(f)
        with open(scenes_path, encoding="utf-8") as f:
            scenes_data = json.load(f)

        transcript_text = "\n".join(
            f"[{t['start']:.0f}s-{t['end']:.0f}s] {t['text']}"
            for t in transcript_data.get("transcript", [])[:200]  # 最多200段
        )
        scenes_text = "\n".join(
            f"[场景{s['id']}] {s['start_sec']:.0f}s-{s['end_sec']:.0f}s, 时长{s['duration_sec']:.0f}秒"
            for s in scenes_data.get("scenes", [])[:50]
        )

        prompt = f"""你是一个电影分析引擎，严格输出JSON，不要解释。

根据以下电影转写文本和镜头切分信息，生成章节摘要。

转写文本（按时间排序）:
{transcript_text}

镜头切分（{len(scenes_data.get('scenes', []))}个镜头）:
{scenes_text}

要求：
1. 将电影分为若干章节（通常8-20章）
2. 每章给出：时间范围、章节标题、核心事件、关键角色
3. 输出严格JSON，格式如下（不要加markdown）：

{{
  "chapters": [
    {{
      "id": 1,
      "title": "",
      "start_sec": 0,
      "end_sec": 300,
      "summary": "",
      "key_events": [],
      "characters": []
    }}
  ],
  "total_duration_sec": 0,
  "genre": "",
  "estimated_theme": ""
}}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个电影分析引擎，严格输出JSON。")
            # 尝试解析JSON
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error="章节摘要解析失败", stage="chapter")
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            num_chapters = len(data.get("chapters", []))
            self._update(f"章节摘要完成，共 {num_chapters} 章", 25)
            return StageResult(success=True, output_path=str(output), data=data, stage="chapter")
        except Exception as e:
            logger.exception("[chapter] Error")
            return StageResult(success=False, error=str(e), stage="chapter")

    # ── Stage 4: 三段式大纲 ─────────────────────────────────────────────────

    def _stage_outline(self, chapters_path: str) -> StageResult:
        """MiniMax 2.7: 章节摘要 → 3段式解说大纲"""
        self._update("正在生成三段式大纲（MiniMax 2.7）...", 30)
        output = self.work_dir / "outline.json"

        with open(chapters_path, encoding="utf-8") as f:
            chapters_data = json.load(f)

        style = self.cfg.style_preset()
        chapters_text = "\n".join(
            f"第{c['id']}章: {c['title']} ({c['start_sec']:.0f}s-{c['end_sec']:.0f}s) - {c['summary']}"
            for c in chapters_data.get("chapters", [])
        )

        prompt = f"""{style['identity']}

任务：根据电影章节摘要，生成3段短视频解说大纲。

要求：
1. 总共3段，每段目标口播时长约{self.cfg.target_duration_per_part_sec//60}分钟
2. 每段要有：开头钩子（hook）、中段推进、结尾悬念
3. 覆盖电影主线剧情，详略得当

风格说明：{style['tone']}
钩子模式：{style['hook_pattern']}

章节摘要:
{chapters_text}

输出严格JSON（不要加markdown）:

{{
  "part1": {{
    "theme": "本段主题",
    "time_range": "对应原片时间段",
    "hook": "开头钩子（20秒内抓住观众）",
    "key_points": ["要点1", "要点2", "要点3"],
    "ending_hook": "结尾悬念（让人想看下一段）"
  }},
  "part2": {{...}},
  "part3": {{...}},
  "overall_arc": "整部电影主线概述"
}}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个电影解说编剧，严格输出JSON。")
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error="大纲生成解析失败", stage="outline")
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._update("三段式大纲生成完成", 35)
            return StageResult(success=True, output_path=str(output), data=data, stage="outline")
        except Exception as e:
            logger.exception("[outline] Error")
            return StageResult(success=False, error=str(e), stage="outline")

    # ── Stage 5: 详细脚本 ───────────────────────────────────────────────────

    def _stage_script(self, outline_path: str, part_num: int) -> StageResult:
        """MiniMax 2.7: 单段详细脚本生成"""
        self._update(f"正在生成第{part_num}段脚本（MiniMax 2.7）...", 35 + part_num * 3)
        output = self.work_dir / "scripts" / f"script_part{part_num}.json"

        with open(outline_path, encoding="utf-8") as f:
            outline = json.load(f)
        part_key = f"part{part_num}"
        if part_key not in outline:
            return StageResult(success=False, error=f"大纲中找不到 {part_key}", stage="script")

        part_data = outline[part_key]
        style = self.cfg.style_preset()

        # Few-shot 示例
        few_shot = ""
        for ex in style.get("examples", []):
            if ex["type"] == "input":
                few_shot += f"\n示例输入:\n{ex['text'][:100]}\n"
            else:
                few_shot += f"示例输出:\n{ex['text'][:200]}\n"

        prompt = f"""{style['identity']}

{few_shot}

任务：根据以下大纲，生成第{part_num}段（约{self.cfg.target_duration_per_part_sec//60}分钟）的详细解说脚本。

风格要求：{style['tone']}
钩子模式：{style['hook_pattern']}

本段大纲:
- 主题: {part_data.get('theme', '')}
- 时间范围: {part_data.get('time_range', '')}
- 开头钩子: {part_data.get('hook', '')}
- 核心要点: {', '.join(part_data.get('key_points', []))}
- 结尾悬念: {part_data.get('ending_hook', '')}

要求：
1. 口语化，适合朗读
2. 每句话长度 15-40 字
3. 节奏感强，信息密度高
4. 避免重复内容
5. 每句话估算时长（秒）

输出严格JSON（不要加markdown）:
{{
  "part_num": {part_num},
  "paragraph_text": "整段脚本的连贯文本（供TTS使用）",
  "sentences": [
    {{
      "id": 1,
      "text": "第一句话",
      "estimated_duration_sec": 4
    }}
  ],
  "total_estimated_duration_sec": 0,
  "hook_strength": 8,
  "pacing_score": 7
}}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个电影解说编剧，严格输出JSON。")
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error=f"第{part_num}段脚本解析失败", stage="script")
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._update(f"第{part_num}段脚本生成完成", 43 + part_num * 3)
            return StageResult(success=True, output_path=str(output), data=data, stage="script")
        except Exception as e:
            logger.exception(f"[script] part{part_num} Error")
            return StageResult(success=False, error=str(e), stage="script")

    # ── Stage 6: Reflection 自检 ───────────────────────────────────────────

    def _stage_reflection(self, script_path: str) -> StageResult:
        """MiniMax 2.7: 脚本自检 + 修正"""
        self._update("正在进行Reflection自检...", 60)
        output = self.work_dir / "final_scripts" / Path(script_path).name

        with open(script_path, encoding="utf-8") as f:
            script_data = json.load(f)

        sentences_text = "\n".join(
            f"句子{i['id']}: {i['text']}（约{i.get('estimated_duration_sec', '?')}秒）"
            for i in script_data.get("sentences", [])
        )
        total_dur = script_data.get("total_estimated_duration_sec", 0)

        style = self.cfg.style_preset()

        prompt = f"""{style['identity']}

请严格检查以下解说脚本，并进行修正。

检查标准：
1. 是否有剧情跳跃（观众会困惑）
2. 是否有冗余信息（重复表达）
3. 是否时长可能超标（目标约{self.cfg.target_duration_per_part_sec//60}分钟={self.cfg.target_duration_per_part_sec}秒，当前估算{total_dur}秒）
4. 开头20秒钩子是否足够强
5. 结尾是否有悬念（让人想看下一段）
6. 每句话是否适合口播（不要太书面）

当前脚本:
{sentences_text}

风格要求：{style['tone']}

输出严格JSON（不要加markdown）:
{{
  "issues_found": ["问题1", "问题2"],
  "issues_fixed": ["修正1", "修正2"],
  "revised_script": {{
    "paragraph_text": "修正后的整段文本",
    "sentences": [
      {{"id": 1, "text": "修正后的句子", "estimated_duration_sec": 4}}
    ],
    "total_estimated_duration_sec": 0
  }},
  "overall_score": 7.5
}}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个严格的内容审核AI，严格输出JSON。")
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error="Reflection解析失败", stage="reflection")
            revised = data.get("revised_script", script_data)
            with open(output, "w", encoding="utf-8") as f:
                json.dump(revised, f, ensure_ascii=False, indent=2)
            issues = data.get("issues_found", [])
            self._update(f"Reflection完成，修正了 {len(issues)} 个问题", 65)
            return StageResult(success=True, output_path=str(output), data=data, stage="reflection")
        except Exception as e:
            logger.exception("[reflection] Error")
            return StageResult(success=False, error=str(e), stage="reflection")

    # ── Stage 7: LLM-as-Judge 评分 ─────────────────────────────────────────

    def _stage_judge(self, final_script_paths: List[str]) -> StageResult:
        """MiniMax 2.7: 批量评分"""
        self._update("正在进行LLM-as-Judge评分...", 70)
        output = self.work_dir / "judge_scores.json"

        all_scripts = []
        for p in final_script_paths:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            all_scripts.append({
                "path": p,
                "part_num": data.get("part_num", "?"),
                "sentences": data.get("sentences", [])[:5],  # 每段取前5句评估
                "total_dur": data.get("total_estimated_duration_sec", 0),
            })

        scripts_text = "\n".join(
            f"第{s['part_num']}段（{s['total_dur']}秒）: " + " | ".join(x['text'] for x in s['sentences'][:3])
            for s in all_scripts
        )

        prompt = f"""你是一个专业的短视频内容质量评估AI，为每个脚本打分。

打分项（每项1-10分）:
- hook_score: 开头钩子强度
- clarity_score: 信息清晰度
- pacing_score: 节奏感
- drama_score: 戏剧张力
- repetition_score: 是否有重复（越高分=越不重复）
- camera_match_score: 是否容易匹配镜头

输出格式（严格JSON，不要markdown）:
{{
  "scores": [
    {{
      "part": 1,
      "hook_score": 8,
      "clarity_score": 7,
      "pacing_score": 8,
      "drama_score": 9,
      "repetition_score": 7,
      "camera_match_score": 6,
      "total_score": 7.8,
      "issues": ["问题1"],
      "recommendation": "PASS/NEED_REVISION"
    }}
  ]
}}

待评估脚本:
{scripts_text}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个严格的内容质量评估AI，严格输出JSON。")
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error="Judge评分解析失败", stage="judge")
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._update("LLM-as-Judge评分完成", 75)
            return StageResult(success=True, output_path=str(output), data=data, stage="judge")
        except Exception as e:
            logger.exception("[judge] Error")
            return StageResult(success=False, error=str(e), stage="judge")

    # ── Stage 8: 镜头提示生成 ───────────────────────────────────────────────

    def _stage_scene_prompts(self, script_path: str, scenes_path: str) -> StageResult:
        """MiniMax 2.7: 为每句旁白生成 HyDE 镜头检索提示"""
        self._update("正在生成镜头提示（HyDE）...", 80)
        # Determine part number from script path: scripts/script_part1.json → part1
        script_name = Path(script_path).name  # e.g. "script_part1.json"
        import re
        m = re.search(r"part(\d+)", script_name)
        part_num = int(m.group(1)) if m else 1
        output = self.work_dir / "scene_prompts" / f"scene_prompts_part{part_num}.json"

        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)
        with open(scenes_path, encoding="utf-8") as f:
            scenes = json.load(f)

        sentences_text = "\n".join(
            f"旁白{i['id']}: {i['text']}"
            for i in script.get("sentences", [])
        )

        prompt = f"""你是一个专业的影视剪辑AI，根据旁白生成检索镜头用的描述。

HyDE方法：先根据旁白生成"理想镜头描述"，再用于场景检索。
不要写抽象评价，要写具体画面：人物、动作、表情、场景、镜头类型。

已知电影镜头列表:
{json.dumps(scenes.get('scenes', [])[:20], ensure_ascii=False, indent=2)}

旁白:
{sentences_text}

输出严格JSON（不要加markdown）:
{{
  "scene_prompts": [
    {{
      "sentence_id": 1,
      "original_narration": "原始旁白",
      "hyde_prompt": "生成的理想镜头描述，用于场景检索。例如：女人在昏暗房间内，镜头从她手中的照片慢慢抬起至她的脸部特写，表现震惊情绪",
      "keywords": ["女人", "房间", "震惊", "特写"],
      "camera_type": "近景"
    }}
  ]
}}"""

        try:
            result_text = self._call_minimax(prompt, system="你是一个专业的影视剪辑AI，严格输出JSON。")
            data = self._extract_json(result_text)
            if not data:
                return StageResult(success=False, error="镜头提示解析失败", stage="scene_prompts")
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            num_prompts = len(data.get("scene_prompts", []))
            self._update(f"镜头提示生成完成，共 {num_prompts} 条", 85)
            return StageResult(success=True, output_path=str(output), data=data, stage="scene_prompts")
        except Exception as e:
            logger.exception("[scene_prompts] Error")
            return StageResult(success=False, error=str(e), stage="scene_prompts")

    # ── Stage 9: 渲染清单 ──────────────────────────────────────────────────

    def _stage_render_manifest(
        self,
        script_paths: List[str],
        prompt_paths: List[str],
        scenes_path: str,
    ) -> StageResult:
        """生成最终渲染清单（FFmpeg 指令集）"""
        self._update("正在生成渲染清单...", 90)
        output = self.work_dir / "render_manifest.json"

        with open(scenes_path, encoding="utf-8") as f:
            scenes = json.load(f)

        manifest = {"parts": [], "global": {}, "ffmpeg_commands": []}

        for i, (sp, pp) in enumerate(zip(script_paths, prompt_paths)):
            with open(sp, encoding="utf-8") as f:
                script = json.load(f)
            with open(pp, encoding="utf-8") as f:
                prompts = json.load(f)

            part_manifest = {
                "part_num": i + 1,
                "narration_audio": f"audio_part{i+1}.mp3",
                "subtitle_file": f"subtitle_part{i+1}.srt",
                "output_file": f"output_part{i+1}.mp4",
                "sentences": [],
            }

            for sent, prompt_data in zip(script.get("sentences", []), prompts.get("scene_prompts", [])):
                hyde = prompt_data.get("hyde_prompt", "")
                # 找最接近时间线的镜头（简单版：按比例映射）
                scenes_list = scenes.get("scenes", [])
                n_scenes = len(scenes_list)
                n_sents = len(script.get("sentences", []))
                scene_idx = min(int((sent['id'] - 1) / n_sents * n_scenes), n_scenes - 1) if n_scenes > 0 else 0

                part_manifest["sentences"].append({
                    "sentence_id": sent["id"],
                    "text": sent["text"],
                    "estimated_dur": sent.get("estimated_duration_sec", 4),
                    "hyde_prompt": hyde,
                    "selected_scene_id": scene_idx,
                    "scene_time_range": (
                        scenes_list[scene_idx]["start_sec"],
                        scenes_list[scene_idx]["end_sec"]
                    ) if scenes_list else (0, 10),
                })

            manifest["parts"].append(part_manifest)

        # 全局渲染参数
        manifest["global"] = {
            "video_codec": "libx264",
            "audio_codec": "aac",
            "resolution": "1920x1080",
            "target_duration_per_part_sec": self.cfg.target_duration_per_part_sec,
        }

        with open(output, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        self._update("渲染清单生成完成，可进入TTS+字幕+渲染阶段", 95)
        return StageResult(success=True, output_path=str(output), data=manifest, stage="render_manifest")

    # ── MiniMax 2.7 调用 ──────────────────────────────────────────────────────

    def _call_minimax(self, prompt: str, system: str = "") -> str:
        """调用 MiniMax 2.7 (OpenAI-compatible API)"""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required: pip install openai")

        client = OpenAI(
            api_key=self.cfg.api_key or os.getenv("OPENAI_API_KEY", ""),
            base_url=self.cfg.api_base or os.getenv("OPENAI_API_BASE", "https://api.minimax.chat/v1"),
        )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        return response.choices[0].message.content

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """从模型输出中提取JSON（处理markdown包裹）"""
        import re
        text = text.strip()
        # 去掉 markdown 代码块
        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^```\s*", "", text)
        text = text.strip()
        # 找 JSON 对象
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return None


# ── 便捷入口 ────────────────────────────────────────────────────────────────

def run_movie_pipeline(
    video_path: str,
    api_key: str = None,
    api_base: str = "https://api.minimax.chat/v1",
    model: str = "MiniMax-2.7-T2I",
    style: str = "悬疑反转",
    style_preset: str = None,
    progress_callback: Callable = None,
    **kwargs,
) -> Dict[str, Any]:
    """一行命令执行完整流水线"""
    cfg = PipelineConfig(
        api_key=api_key or os.getenv("OPENAI_API_KEY", ""),
        api_base=api_base,
        model=model,
        style=style or style_preset or DEFAULT_STYLE,
        **kwargs,
    )
    pipeline = MovieNarrationPipeline(cfg)
    if progress_callback:
        pipeline.set_progress_callback(progress_callback)
    return pipeline.run(video_path)
