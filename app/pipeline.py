"""
RedditNarratoAI 核心流水线
Reddit帖子 → AI文案改写 → TTS配音 → 字幕 → 视频剪辑
"""

import os
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from pathlib import Path
from loguru import logger

from app.config import config
from app.services.reddit import RedditFetcher, RedditContent
from app.services.llm import generate_script
from app.services.voice import generate_voice
from app.services.subtitle import create_srt_from_text


@dataclass
class VideoSegment:
    """视频片段"""
    text: str
    audio_path: str = ""
    subtitle_path: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    image_path: str = ""


@dataclass
class PipelineResult:
    """流水线结果"""
    success: bool
    video_path: str = ""
    audio_path: str = ""
    script: str = ""
    segments: List[VideoSegment] = field(default_factory=list)
    error: str = ""


class RedditVideoPipeline:
    """
    Reddit视频流水线
    
    流程:
    1. RedditFetcher 获取帖子/评论
    2. LLM 改写为解说文案
    3. TTS 生成配音
    4. 字幕生成
    5. 视频剪辑合成
    """
    
    def __init__(self, config_dict: dict):
        """
        初始化流水线
        
        Args:
            config_dict: 配置字典
        """
        self.config = config_dict
        self.reddit_fetcher = RedditFetcher(config_dict)
        self.output_dir = Path(config_dict.get("app", {}).get("output_dir", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 回调函数用于进度更新
        self._progress_callback: Optional[Callable] = None
        
    def set_progress_callback(self, callback: Callable[[str, int], None]):
        """设置进度回调函数"""
        self._progress_callback = callback
        
    def _update_progress(self, step: str, percent: int):
        """更新进度"""
        logger.info(f"[{percent}%] {step}")
        if self._progress_callback:
            self._progress_callback(step, percent)
    
    def run(self, url_or_id: str, use_story_mode: bool = True, bilibili_cookies: str = None) -> PipelineResult:
        """
        运行完整流水线

        Args:
            url_or_id: Reddit帖子URL/ID，或B站 BV 号
            use_story_mode: 是否使用故事模式（帖子作为开头，评论作为内容）
            bilibili_cookies: B站 cookies 文本（用于高清下载）

        Returns:
            PipelineResult: 处理结果
        """
        # Detect B站 video
        bv_id = self._detect_bilibili(url_or_id)
        if bv_id:
            return self._run_bilibili(bv_id, bilibili_cookies)

        result = PipelineResult(success=False)
        session_id = str(uuid.uuid4())[:8]

        try:
            # Step 1: 获取Reddit内容
            self._update_progress("正在获取Reddit内容...", 10)
            content = self.reddit_fetcher.fetch_by_url(url_or_id)
            if not content:
                result.error = "无法获取Reddit内容，请检查URL或凭证"
                return result

            logger.info(f"获取到帖子: {content.thread_title}")
            logger.info(f"评论数: {len(content.comments)}")
            
            # Step 2: 生成解说文案
            self._update_progress("正在生成AI解说文案...", 30)
            script = self._generate_script(content, use_story_mode)
            if not script:
                result.error = "AI文案生成失败"
                return result
            result.script = script
            
            # Step 3: 生成配音
            self._update_progress("正在生成TTS配音...", 50)
            audio_path, segments = self._generate_voice(script, session_id)
            if not audio_path:
                result.error = "TTS配音生成失败"
                return result
            result.audio_path = audio_path
            result.segments = segments
            
            # Step 4: 生成字幕
            self._update_progress("正在生成字幕...", 70)
            subtitle_path = self._generate_subtitle(script, segments, session_id)
            result.segments = segments
            
            # Step 5: 合成视频
            self._update_progress("正在合成视频...", 85)
            video_path = self._create_video(
                segments=segments,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                session_id=session_id,
                content=content
            )
            
            if video_path and os.path.exists(video_path):
                result.success = True
                result.video_path = video_path
                self._update_progress("视频生成完成!", 100)
            else:
                result.error = "视频合成失败"
                
        except Exception as e:
            logger.exception("流水线执行出错")
            result.error = str(e)
            
        return result
    
    def _detect_bilibili(self, url_or_id: str) -> str:
        """检测是否为B站视频URL或BV号"""
        import re
        url_or_id = url_or_id.strip()
        # BV号格式: BV1xx4y1X7z2
        bv_match = re.match(r"^BV[A-Za-z0-9]{10}$", url_or_id)
        if bv_match:
            return url_or_id
        # bilibili.com/video/BVxxx
        bv_in_url = re.search(r"BV[A-Za-z0-9]{10}", url_or_id)
        if bv_in_url:
            return bv_in_url.group()
        return None

    def _run_bilibili(self, bv_id: str, cookies_text: str = None) -> PipelineResult:
        """B站视频处理流程"""
        from app.services.bilibili import download_with_cookies_flow
        import tempfile

        result = PipelineResult(success=False)
        try:
            tmp_dir = tempfile.mkdtemp(prefix="bili_")
            self._update_progress(f"正在下载B站视频 {bv_id}...", 15)

            dl_result = download_with_cookies_flow(
                bv_id=bv_id,
                output_dir=tmp_dir,
                cookies_text=cookies_text,
                quality="1080",
                progress_callback=lambda msg, pct: self._update_progress(msg, pct),
            )

            if not dl_result["success"]:
                result.error = dl_result.get("error", "B站下载失败")
                return result

            video_path = dl_result["video_path"]
            subtitle_path = dl_result.get("subtitle_path", "")

            self._update_progress("正在生成配音...", 60)

            # B站视频本身有字幕，不需要AI改写文案，直接用字幕
            # 如果有字幕文件，读取字幕内容作为script
            script = ""
            if subtitle_path and os.path.exists(subtitle_path):
                try:
                    import srt
                    with open(subtitle_path, encoding="utf-8") as f:
                        subs = list(srt.parse(f.read()))
                    script = " ".join(sub.content for sub in subs)
                except Exception:
                    pass

            if not script:
                script = f"这是B站视频 {bv_id} 的解说内容。"

            self._update_progress("正在合成配音和字幕...", 80)

            # 如果有字幕，合成到视频
            if subtitle_path and os.path.exists(subtitle_path):
                output_path = video_path.replace("_final.mp4", "_with_sub.mp4")
                from app.services.video import replace_video_audio_and_subtitle
                replace_video_audio_and_subtitle(
                    video_path=video_path,
                    audio_path=None,  # B站视频已有音轨
                    subtitle_path=subtitle_path,
                    output_path=output_path,
                )
                video_path = output_path
                self._update_progress("完成", 100)
            else:
                self._update_progress("完成（无字幕）", 100)

            result.success = True
            result.video_path = video_path
            result.script = script
            logger.info(f"[bilibili pipeline] Done: {bv_id}")
            return result

        except Exception as e:
            logger.exception("[bilibili pipeline] Error")
            result.error = str(e)
            return result

    def _generate_script(self, content: RedditContent, use_story_mode: bool) -> str:
        """
        使用LLM生成解说文案
        
        Args:
            content: Reddit内容
            use_story_mode: 是否故事模式
            
        Returns:
            str: 生成的解说文案
        """
        # 准备上下文
        if use_story_mode and content.comments:
            # 故事模式：帖子是问题，评论是回答
            comments_text = "\n".join([
                f"- {c['comment_body'][:200]}" 
                for c in content.comments[:5]  # 最多5条评论
            ])
            prompt = f"""你是一个影视解说博主。请将下面的Reddit帖子和评论改写成吸引人的解说文案。

帖子标题: {content.thread_title}
帖子内容: {content.thread_post or '无'}

热门评论:
{comments_text}

要求:
1. 前3句必须吸引人，像短视频爆款开头
2. 文案长度2-4分钟朗读时长
3. 将评论中的精彩回答融入解说
4. 语言生动，口语化，适合朗读
5. 不要出现"Reddit"、"帖子"、"评论"等词，用"他"、"这个人"、"故事"等代替

请直接输出解说文案，不要加标题或说明:
"""
        else:
            # 非故事模式：只用帖子内容
            prompt = f"""你是一个影视解说博主。请将下面的Reddit帖子改写成吸引人的解说文案。

帖子标题: {content.thread_title}
帖子内容: {content.thread_post or '无'}

要求:
1. 前3句必须吸引人，像短视频爆款开头
2. 文案长度2-4分钟朗读时长
3. 语言生动，口语化，适合朗读
4. 不要出现"Reddit"、"帖子"等词

请直接输出解说文案，不要加标题或说明:
"""
        
        try:
            script = generate_script(
                prompt=prompt,
                config=self.config,
                system_prompt="你是一个专业的影视解说博主，擅长将网络内容改写成吸引人的短视频文案。"
            )
            return script.strip()
        except Exception as e:
            logger.error(f"LLM生成失败: {e}")
            return ""
    
    def _generate_voice(self, script: str, session_id: str) -> tuple:
        """
        生成TTS配音
        
        Returns:
            (audio_path, segments)
        """
        try:
            audio_path, durations = generate_voice(
                text=script,
                output_dir=str(self.output_dir / session_id),
                config=self.config
            )
            
            # 根据duration切分segments
            segments = []
            current_time = 0.0
            texts = script.split('\n')
            texts = [t.strip() for t in texts if t.strip()]
            
            for i, text in enumerate(texts):
                duration = durations[i] if i < len(durations) else 3.0
                segments.append(VideoSegment(
                    text=text,
                    audio_path=audio_path,
                    start_time=current_time,
                    end_time=current_time + duration
                ))
                current_time += duration
                
            return audio_path, segments
            
        except Exception as e:
            logger.error(f"TTS生成失败: {e}")
            return "", []
    
    def _generate_subtitle(self, script: str, segments: list, session_id: str) -> str:
        """生成字幕文件"""
        try:
            subtitle_path = str(self.output_dir / session_id / "subtitle.srt")
            create_srt_from_text(
                text=script,
                output_path=subtitle_path,
                config=self.config
            )
            return subtitle_path
        except Exception as e:
            logger.error(f"字幕生成失败: {e}")
            return ""
    
    def _create_video(
        self, 
        segments: List[VideoSegment],
        audio_path: str,
        subtitle_path: str,
        session_id: str,
        content: RedditContent
    ) -> str:
        """合成最终视频"""
        try:
            from app.services.video import create_video_from_segments
            
            video_path = create_video_from_segments(
                segments=segments,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                output_dir=str(self.output_dir / session_id),
                config=self.config,
                title=content.thread_title
            )
            return video_path or ""
        except Exception as e:
            logger.error(f"视频合成失败: {e}")
            return ""


def run_pipeline(
    reddit_url: str = None,
    bilibili_id: str = None,
    bilibili_cookies: str = None,
    config_dict: dict = None,
    progress_callback: Optional[Callable] = None
) -> PipelineResult:
    """
    便捷函数：运行完整流水线
    """
    pipeline = RedditVideoPipeline(config_dict)
    if progress_callback:
        pipeline.set_progress_callback(progress_callback)
    return pipeline.run(
        reddit_url or bilibili_id,
        bilibili_cookies=bilibili_cookies,
    )


def run_local_video_pipeline(
    video_path: str,
    config_dict: dict,
    progress_callback: Optional[Callable] = None,
    split_video: bool = False,
    video_description: str = None,
) -> PipelineResult:
    """
    本地视频模式流水线：
    视频上传 → AI配音 → SRT字幕 → 烧录音频+字幕到视频 → 可选智能切片

    Args:
        video_path: 本地视频文件路径
        config_dict: 配置字典
        progress_callback: 进度回调函数
        split_video: 是否启用智能分段（自动找自然停顿点，每段独立配音）
        video_description: 视频内容描述（可选，用于AI生成更精准的解说）

    Returns:
        PipelineResult: {success, video_path, script, error}
    """
    import os
    from app.services.voice import generate_voice
    from app.services.subtitle import create_srt_from_text
    from app.services.video import replace_video_audio_and_subtitle, find_silence_boundaries

    result = PipelineResult(success=False)

    def _update(msg: str, pct: int):
        if progress_callback:
            progress_callback(msg, pct)
        logger.info(f"[{pct}%] {msg}")

    try:
        if not os.path.exists(video_path):
            result.error = f"视频文件不存在: {video_path}"
            return result

        from moviepy import VideoFileClip
        video_clip = VideoFileClip(video_path)
        total_duration = video_clip.duration
        video_clip.close()

        output_dir = os.path.join(config_dict.get("app", {}).get("output_dir", "./output"), "local_video")
        os.makedirs(output_dir, exist_ok=True)

        # ─── 智能分段模式：Whisper分析 + 高光检测 + 每段独立配音 ───
        if split_video and total_duration > 90:
            from app.services.audio_analysis import analyze_video_content, find_highlight_segments

            _update("正在用 Whisper 分析视频内容...", 5)

            # Step 1: Whisper 自动分析（转写 + 内容描述 + 高光分段）
            analysis = analyze_video_content(
                video_path=video_path,
                progress_callback=lambda msg, pct: _update(f"[Whisper] {msg}", pct),
            )

            # 优先用 AI 自动生成的内容描述，用户填写则合并
            auto_description = analysis.get("description", "")
            if video_description and auto_description:
                # 合并：用户描述补充 AI 描述
                final_description = f"{auto_description}\n\n用户补充：{video_description}"
            elif video_description:
                final_description = video_description
            else:
                final_description = auto_description

            # 获取分段点：高光检测 > 静音检测 > uniform fallback
            whisper_segments = analysis.get("segments", [])
            if whisper_segments:
                segments = whisper_segments
                logger.info(f"[smart split] Using Whisper/highlight segments: {segments}")
            else:
                # fallback: 高光检测
                _update("正在检测高光片段...", 20)
                hl = find_highlight_segments(
                    video_path=video_path,
                    min_peak_gap=45.0,
                    energy_percentile=0.75,
                    min_segment_duration=60.0,
                    max_segment_duration=240.0,
                )
                segments = [(s, e) for s, e, _ in hl]
                if not segments:
                    # 最后 fallback: 静音检测
                    _update("使用静音检测分段...", 25)
                    segments = find_silence_boundaries(
                        video_path,
                        min_silence_duration=0.8,
                        silence_threshold_db=-40.0,
                        min_segment_duration=60.0,
                        max_segment_duration=240.0,
                    )

            num_segments = len(segments)
            _update(f"视频分析完成，共 {num_segments} 个片段，开始逐段生成配音...", 30)

            from app.services.llm import generate_script_simple
            clips_dir = os.path.join(output_dir, "smart_clips")
            os.makedirs(clips_dir, exist_ok=True)

            all_scripts = []
            whisper_transcript = analysis.get("transcript", "")

            for i, (seg_start, seg_end) in enumerate(segments):
                seg_dur = seg_end - seg_start
                seg_pct_base = 30 + int(65 * i / num_segments)

                _update(f"片段 {i+1}/{num_segments}：生成解说文案 ({seg_dur:.0f}秒)...", seg_pct_base)

                # 构建该片段的解说 Prompt（融合 Whisper 转写内容）
                seg_idx_display = i + 1
                seg_prompt = (
                    f"你是一个影视解说博主。为视频的第{seg_idx_display}个片段写一段中文解说文案。\n"
                    f"该片段时长约 {seg_dur:.0f} 秒。\n"
                    f"风格要求：生动有趣，适合短视频平台，每段话要有头有尾，逻辑完整。\n"
                )
                if whisper_transcript:
                    # 加入该片段对应时间范围内的转写片段作为参考
                    seg_transcript_parts = []
                    for seg in analysis.get("whisper_segments", []):
                        if seg.get("start", 0) >= seg_start - 5 and seg.get("end", 0) <= seg_end + 5:
                            seg_transcript_parts.append(seg["text"])
                    if seg_transcript_parts:
                        seg_prompt += f"\n该片段的语音内容（参考）：{' '.join(seg_transcript_parts[:5])}"
                if final_description:
                    seg_prompt += f"\n\n视频背景：{final_description[:500]}"

                script = generate_script_simple(seg_prompt, config_dict)
                if not script or len(script.strip()) < 5:
                    script = "让我们继续看看接下来发生了什么！"
                script = script.strip()
                all_scripts.append(script)

                _update(f"片段 {i+1}/{num_segments}：生成配音...", seg_pct_base + 12)

                # 生成配音
                seg_output_dir = os.path.join(clips_dir, f"seg_{i:03d}")
                os.makedirs(seg_output_dir, exist_ok=True)
                audio_path, durations = generate_voice(script, seg_output_dir, config_dict)
                if not audio_path or not os.path.exists(audio_path):
                    logger.warning(f"[smart split] TTS failed for segment {i+1}, skipping audio")
                    audio_path = None
                    durations = []

                _update(f"片段 {i+1}/{num_segments}：生成字幕...", seg_pct_base + 20)

                subtitle_path = None
                if audio_path and durations:
                    subtitle_path = create_srt_from_text(script, durations, seg_output_dir)

                _update(f"片段 {i+1}/{num_segments}：合成视频片段...", seg_pct_base + 25)

                clip_output = os.path.join(clips_dir, f"clip_{i:03d}.mp4")
                _render_segment(
                    video_path=video_path,
                    seg_start=seg_start,
                    seg_end=seg_end,
                    audio_path=audio_path,
                    subtitle_path=subtitle_path,
                    output_path=clip_output,
                    seg_script=script,
                    config_dict=config_dict,
                )
                _update(f"片段 {i+1}/{num_segments} 完成", seg_pct_base + 35)

            # 附上 Whisper 完整转写
            full_script = ""
            if whisper_transcript:
                full_script = f"【Whisper 完整转写】\n{whisper_transcript}\n\n"
            full_script += "\n\n---\n\n".join(all_scripts)

            result.success = True
            result.video_path = clips_dir
            result.script = full_script
            _update(f"全部 {num_segments} 个片段生成完毕！", 100)
            logger.info(f"[smart split] Done: {num_segments} clips in {clips_dir}")
            return result

        # ─── 普通模式：整段一个配音 ───
        _update("正在生成AI解说文案...", 10)

        script_prompt = (
            "你是一个影视解说博主。请为这段视频写一段中文解说文案，"
            "风格生动有趣，适合短视频平台。注意：不需要描述画面，只写解说词。"
        )
        if video_description:
            script_prompt += f"\n视频背景：{video_description}"
        from app.services.llm import generate_script_simple
        script = generate_script_simple(script_prompt, config_dict)
        if not script:
            script = "这是一段精彩的视频内容，让我们一起来看看吧。"
        _update(f"文案生成完成 ({len(script)}字)", 30)

        _update("正在生成配音...", 50)
        audio_path, durations = generate_voice(script, output_dir, config_dict)
        if not audio_path or not os.path.exists(audio_path):
            result.error = "语音生成失败"
            return result
        _update("配音生成完成", 70)

        _update("正在生成字幕...", 80)
        subtitle_path = create_srt_from_text(script, durations or [], output_dir)
        _update("字幕生成完成", 85)

        _update("正在合成最终视频...", 88)
        final_path = os.path.join(output_dir, "final_with_audio.mp4")

        if split_video and total_duration > 90:
            # 固定3分钟切（兼容模式）
            tmp_final = os.path.join(output_dir, "tmp_full.mp4")
            replace_video_audio_and_subtitle(
                video_path=video_path,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                output_path=tmp_final,
            )
            _update("正在切片...", 93)

            from app.services.video import split_video_into_clips
            clips_dir = os.path.join(output_dir, "clips")
            clips = split_video_into_clips(
                video_path=tmp_final,
                output_dir=clips_dir,
                max_duration=180.0,
                overlap=3.0,
            )
            result.success = True
            result.video_path = clips_dir
            result.script = script
            _update(f"切片完成，共 {len(clips)} 个片段", 100)
            logger.info(f"[local video pipeline] Split into {len(clips)} clips")
            return result
        else:
            replace_video_audio_and_subtitle(
                video_path=video_path,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                output_path=final_path,
            )
            _update("视频合成完成", 100)

        result.success = True
        result.video_path = final_path
        result.script = script
        logger.info(f"[local video pipeline] Done: {final_path}")
        return result

    except Exception as e:
        logger.exception("本地视频处理失败")
        result.error = str(e)
        return result


def _render_segment(
    video_path: str,
    seg_start: float,
    seg_end: float,
    audio_path: str,
    subtitle_path: str,
    output_path: str,
    seg_script: str,
    config_dict: dict,
) -> str:
    """
    渲染单个视频片段：截取原视频 + 替换/混合音频 + 烧录字幕
    使用 FFmpeg（已安装）处理，避免 moviepy 字幕烧录的兼容性问题
    """
    import subprocess, os

    try:
        seg_dur = seg_end - seg_start

        # 构建 FFmpeg 命令：先切片段，再烧字幕
        cmd = ["ffmpeg", "-y"]

        # 输入1：原始视频（做视频轨道）
        cmd += ["-i", video_path]

        # 输入2：新配音音频（如果有）
        if audio_path and os.path.exists(audio_path):
            cmd += ["-i", audio_path]

        # 时间范围：只取片段部分
        cmd += ["-ss", str(seg_start), "-t", str(seg_dur)]

        # 视频流：直接拷贝（不重新编码）
        cmd += ["-map", "0:v"]

        if audio_path and os.path.exists(audio_path):
            # 音频用配音替换
            cmd += ["-map", "1:a"]
        else:
            # 保留原音
            cmd += ["-map", "0:a?"]

        cmd += [
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]

        logger.info(f"[_render_segment] ffmpeg: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if proc.returncode != 0:
            logger.warning(f"[_render_segment] ffmpeg failed: {proc.stderr[-200:]}")
            # Fallback: moviepy
            from moviepy import VideoFileClip, AudioFileClip
            video = VideoFileClip(video_path).subclipped(seg_start, seg_end)
            if audio_path and os.path.exists(audio_path):
                new_audio = AudioFileClip(audio_path)
                if new_audio.duration > video.duration:
                    new_audio = new_audio.subclipped(0, video.duration)
                from moviepy import CompositeAudioClip
                final_audio = CompositeAudioClip([video.audio, new_audio]) if video.audio else new_audio
            else:
                final_audio = video.audio
            final_video = video.with_audio(final_audio)
            final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", threads=2, logger=None)
            final_video.close()
            if audio_path:
                new_audio.close()
            video.close()
        else:
            logger.info(f"[_render_segment] Written: {output_path}")

        # 烧录字幕（FFmpegassubs）
        if subtitle_path and os.path.exists(subtitle_path):
            sub_output = output_path.replace(".mp4", "_sub.mp4")
            sub_cmd = [
                "ffmpeg", "-y",
                "-i", output_path,
                "-vf", f"subtitles='{subtitle_path}':force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'",
                "-c:a", "copy",
                sub_output,
            ]
            logger.info(f"[_render_segment] burning subs: {' '.join(sub_cmd)}")
            sub_proc = subprocess.run(sub_cmd, capture_output=True, text=True, timeout=300)
            if sub_proc.returncode == 0 and os.path.exists(sub_output):
                os.replace(sub_output, output_path)
                logger.info(f"[_render_segment] subtitles burned")
            else:
                logger.warning(f"[_render_segment] subtitle burn failed: {sub_proc.stderr[-200:]}")

        return output_path

    except Exception as e:
        logger.exception(f"[_render_segment] Error rendering {output_path}")
        try:
            from moviepy import VideoFileClip
            video = VideoFileClip(video_path).subclipped(seg_start, seg_end)
            video.write_videofile(output_path, codec="libx264", audio_codec="aac", threads=2, logger=None)
            video.close()
        except:
            pass
        return output_path

