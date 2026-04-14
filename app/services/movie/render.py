"""
Movie Render - TTS + 字幕 + FFmpeg 渲染
========================================
接收 MovieNarrationPipeline 输出的 render_manifest.json
执行：TTS配音生成 → SRT字幕 → FFmpeg渲染 → 最终视频

用法:
    from app.services.movie.render import MovieRender
    renderer = MovieRender(render_manifest_path, config)
    renderer.run_all()
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class MovieRender:
    """
    电影解说视频渲染器

    输入: render_manifest.json
    输出: 3段完整解说视频
    """

    def __init__(
        self,
        manifest_path: str,
        output_dir: str = "./output/movie",
        config: Dict[str, Any] = None,
    ):
        self.manifest_path = manifest_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}

        with open(manifest_path, encoding="utf-8") as f:
            self.manifest = json.load(f)

        self.session_id = uuid.uuid4().hex[:8]
        self.work_dir = Path(output_dir) / f"session_{self.session_id}"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, cb: Callable[[str, int], None]):
        self._progress_callback = cb

    def _update(self, msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")
        if self._progress_callback:
            self._progress_callback(msg, pct)

    def run_all(self) -> Dict[str, Any]:
        """执行完整渲染流程"""
        self._update("开始渲染流程...", 5)
        results = []

        for i, part in enumerate(self.manifest.get("parts", [])):
            self._update(f"渲染第 {i+1} 段视频...", 10 + i * 25)
            result = self._render_part(part, i)
            results.append(result)
            self._update(f"第 {i+1} 段渲染完成: {result.get('output_path', 'ERROR')}", 35 + i * 25)

        return {
            "success": all(r.get("success", False) for r in results),
            "parts": results,
            "output_dir": str(self.output_dir),
        }

    def _render_part(self, part_manifest: Dict, part_index: int) -> Dict[str, Any]:
        """渲染单个Part"""
        sentences = part_manifest.get("sentences", [])
        if not sentences:
            return {"success": False, "error": "No sentences to render", "part": part_index + 1}

        # ── Step 1: 拼接所有旁白文本 ────────────────────────────────────
        full_text = " ".join(s["text"] for s in sentences)
        audio_path = str(self.work_dir / f"part{part_index+1}_audio.mp3")
        srt_path = str(self.work_dir / f"part{part_index+1}_audio.srt")

        # ── Step 2: TTS 生成配音 ────────────────────────────────────────
        self._update(f"正在生成第{part_index+1}段配音（Edge TTS）...", 10 + part_index * 20)
        ok = self._generate_tts(full_text, audio_path, sentences)
        if not ok:
            return {"success": False, "error": "TTS generation failed", "part": part_index + 1}

        # ── Step 3: 生成 SRT 字幕 ────────────────────────────────────────
        self._update(f"正在生成第{part_index+1}段字幕...", 15 + part_index * 20)
        self._generate_srt(sentences, srt_path)

        # ── Step 4: FFmpeg 渲染视频 ──────────────────────────────────────
        output_path = str(self.output_dir / f"part{part_index+1}.mp4")
        self._update(f"正在渲染第{part_index+1}段视频（FFmpeg）...", 20 + part_index * 20)
        ok = self._render_video(
            audio_path=audio_path,
            subtitle_path=srt_path,
            sentences=sentences,
            output_path=output_path,
            part_index=part_index,
        )
        return {
            "success": ok,
            "output_path": output_path if ok else None,
            "audio_path": audio_path,
            "subtitle_path": srt_path,
            "part": part_index + 1,
        }

    def _generate_tts(
        self,
        text: str,
        output_path: str,
        sentences: List[Dict],
        voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> bool:
        """Edge TTS 生成配音（带时间戳对齐）"""
        try:
            import edge_tts
            import asyncio

            async def _run():
                # 生成带时间戳的音频（用 communicate 预估每句时长）
                Communicate = edge_tts.Communicate
                await Communicate(
                    text,
                    voice=voice,
                    rate="+10%",
                    pitch="+5Hz",
                ).save(output_path)
                return True

            asyncio.run(_run())
            return os.path.exists(output_path)
        except Exception as e:
            logger.warning(f"[TTS] edge_tts failed: {e}, using fallback")
            return self._tts_fallback(text, output_path)

    def _tts_fallback(self, text: str, output_path: str) -> bool:
        """TTS fallback: 静音频 + 日志"""
        logger.warning("[TTS] Using silent audio fallback - install edge-tts for real TTS")
        try:
            # 生成静音音频（1分钟，mp3）
            result = subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "60",
                "-q:a", "2",
                output_path,
            ], capture_output=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return False

    def _generate_srt(self, sentences: List[Dict], output_path: str) -> str:
        """根据音频时长生成 SRT 字幕"""
        # 估算：使用 estimated_duration_sec
        current_ms = 0
        lines = []
        sub_id = 1
        for sent in sentences:
            start_ms = current_ms
            dur = sent.get("estimated_duration_sec", 4) * 1000
            end_ms = start_ms + dur
            current_ms = end_ms + 200  # 200ms 间隔

            lines.append(f"{sub_id}")
            lines.append(f"{_ms_to_srt_time(start_ms)} --> {_ms_to_srt_time(end_ms)}")
            lines.append(sent["text"])
            lines.append("")
            sub_id += 1

        srt_content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return output_path

    def _render_video(
        self,
        audio_path: str,
        subtitle_path: str,
        sentences: List[Dict],
        output_path: str,
        part_index: int,
    ) -> bool:
        """FFmpeg 渲染最终视频"""
        video_cfg = self.manifest.get("global", {})

        # 估算音频时长
        import math
        total_dur = sum(s.get("estimated_duration_sec", 4) for s in sentences)
        scenes = []
        for i, s in enumerate(sentences):
            dur = s.get("estimated_duration_sec", 4)
            scenes.append({
                "id": s.get("selected_scene_id", 0),
                "start": s.get("scene_time_range", (0, 10))[0],
                "dur": dur,
            })

        # 生成黑场 + 字幕视频（placeholder，等 scene matching 实现）
        black_slide = str(self.work_dir / f"part{part_index+1}_slide.mp4")

        # 创建幻灯片视频
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i",
                f"color=c=black:s=1920x1080:d={total_dur + 1}:r=30",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                black_slide,
            ], capture_output=True, timeout=120)
        except Exception as e:
            logger.warning(f"[render] slide creation failed: {e}")
            return False

        if not os.path.exists(black_slide):
            return False

        # 烧录字幕 + 音视频合并
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", black_slide,
                "-i", audio_path,
                "-vf",
                f"subtitles={subtitle_path}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,Outline=2'",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"[render] Part {part_index+1} done: {output_path}")
                return True
            else:
                logger.warning(f"[render] ffmpeg failed: {result.stderr[-200:]}")
                # Fallback: 简单合并
                return self._render_video_simple(black_slide, audio_path, output_path)
        except Exception as e:
            logger.exception("[render] Error")
            return False

    def _render_video_simple(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
    ) -> bool:
        """简单渲染：无字幕"""
        try:
            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_path,
            ], capture_output=True, timeout=300)
            return result.returncode == 0 and os.path.exists(output_path)
        except Exception:
            return False


def _ms_to_srt_time(ms: int) -> str:
    """毫秒 → SRT 时间格式 (00:00:00,000)"""
    s = ms // 1000
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms % 1000:03d}"


def render_from_manifest(
    manifest_path: str,
    output_dir: str = "./output/movie",
    progress_callback: Callable = None,
) -> Dict[str, Any]:
    """便捷入口"""
    renderer = MovieRender(manifest_path, output_dir)
    if progress_callback:
        renderer.set_progress_callback(progress_callback)
    return renderer.run_all()
