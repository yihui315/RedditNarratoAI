"""
RedditNarratoAI 核心流水线 (Agentic Engineering 版本)
Reddit帖子 → AI文案改写（Subagent 并行） → TTS配音 → 动态字幕 → B-roll + BGM + 转场 → 视频

特性:
- Subagent 并行处理（评论总结、情绪曲线、B-roll 关键词）
- Verification Loop 每步自动验证
- 动态字幕 + B-roll + BGM + 转场
- Graceful degradation（缺少资源时降级）
"""

import os
import re
import json
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Dict
from pathlib import Path
from loguru import logger

from app.services.reddit import RedditFetcher, RedditContent
from app.services.voice import generate_voice
from app.services.subtitle import create_srt_from_text
from app.verification import VerificationLoop


@dataclass
class VideoSegment:
    """视频片段"""
    text: str
    audio_path: str = ""
    subtitle_path: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    image_path: str = ""
    mood: str = "calm"
    broll_keywords: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """流水线结果"""
    success: bool
    video_path: str = ""
    audio_path: str = ""
    script: str = ""
    segments: List[VideoSegment] = field(default_factory=list)
    timeline: List[dict] = field(default_factory=list)
    error: str = ""
    verification_log: List[str] = field(default_factory=list)


# --- LLM Helper ---

def _call_llm(prompt: str, config_dict: dict, system_prompt: str = "") -> str:
    """
    调用 LLM 生成文本（使用 config.toml 中的 [llm] 配置）

    支持 OpenAI 兼容 API（包括 Ollama）。
    """
    llm_config = config_dict.get("llm", {})
    api_base = llm_config.get("api_base", "http://localhost:11434/v1")
    api_key = llm_config.get("api_key", "not-needed")
    model = llm_config.get("model", "deepseek-r1:32b")
    max_tokens = llm_config.get("max_tokens", 4096)
    temperature = llm_config.get("temperature", 0.7)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=api_base)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return ""


# --- Subagent 并行任务 ---

async def _subagent_summarize_comments(comments: list, config_dict: dict) -> str:
    """Subagent 1: 评论总结"""
    if not comments:
        return "无热门评论。"

    comments_text = "\n".join([
        f"- {c['comment_body'][:200]}"
        for c in comments[:10]
    ])

    prompt = f"""请总结以下评论的核心观点，提炼最有故事性的内容，用2-3句话概括：

{comments_text}

直接输出总结，不要加前缀或说明:"""

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _call_llm, prompt, config_dict, "你是一个内容分析专家。"
    )


async def _subagent_emotion_curve(title: str, body: str, config_dict: dict) -> List[dict]:
    """Subagent 2: 情绪曲线生成"""
    prompt = f"""分析以下内容的情绪走向，输出 JSON 数组，每个元素包含 paragraph_hint（段落内容提示）和 mood（情绪标签，只能是 tense/emotional/upbeat/calm 之一）。

标题: {title}
内容: {body[:500] if body else '无'}

输出纯 JSON 数组，不要其他内容。至少3个元素。示例格式:
[{{"paragraph_hint": "开头悬念", "mood": "tense"}}, {{"paragraph_hint": "情感转折", "mood": "emotional"}}, {{"paragraph_hint": "结尾", "mood": "upbeat"}}]"""

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _call_llm, prompt, config_dict, "你是一个情绪分析专家，只输出 JSON。"
    )

    try:
        # 尝试提取 JSON
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    # 降级：返回默认曲线
    return [
        {"paragraph_hint": "开头", "mood": "tense"},
        {"paragraph_hint": "发展", "mood": "emotional"},
        {"paragraph_hint": "高潮", "mood": "upbeat"},
        {"paragraph_hint": "结尾", "mood": "calm"},
    ]


async def _subagent_broll_keywords(title: str, body: str, config_dict: dict) -> List[dict]:
    """Subagent 3: B-roll 关键词匹配"""
    prompt = f"""为以下内容的每个段落建议1-2个适合搜索B-roll视频的英文关键词。输出 JSON 数组。

标题: {title}
内容: {body[:500] if body else '无'}

输出纯 JSON 数组，不要其他内容。至少3个元素。示例格式:
[{{"paragraph_hint": "开头", "keywords": ["mystery", "dark room"]}}, {{"paragraph_hint": "发展", "keywords": ["city street", "crowd"]}}, {{"paragraph_hint": "结尾", "keywords": ["sunrise", "hope"]}}]"""

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _call_llm, prompt, config_dict, "你是一个视频制作专家，只输出 JSON。"
    )

    try:
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    return [
        {"paragraph_hint": "开头", "keywords": ["dramatic", "mystery"]},
        {"paragraph_hint": "发展", "keywords": ["people", "city"]},
        {"paragraph_hint": "结尾", "keywords": ["sunrise", "hope"]},
    ]


# --- Script 解析工具 ---

def parse_annotated_script(script: str) -> List[dict]:
    """
    解析带标注的文案，提取每段的文本、情绪和 B-roll 关键词

    Returns:
        [{text, mood, broll_keywords}, ...]
    """
    paragraphs = [p.strip() for p in script.split('---') if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in script.split('\n') if p.strip()]

    result = []
    for para in paragraphs:
        # 提取 mood
        mood_match = re.search(r'\[mood:(\w+)\]', para)
        mood = mood_match.group(1) if mood_match else "calm"

        # 提取 broll keywords
        broll_match = re.search(r'\[broll:([^\]]+)\]', para)
        broll_keywords = []
        if broll_match:
            broll_keywords = [k.strip() for k in broll_match.group(1).split(',')]

        # 清理标注
        clean_text = re.sub(r'\[(?:mood|broll):[^\]]*\]', '', para).strip()

        if clean_text:
            result.append({
                "text": clean_text,
                "mood": mood,
                "broll_keywords": broll_keywords,
            })

    return result


# --- Pipeline ---

class RedditVideoPipeline:
    """
    Reddit视频流水线 (Agentic Engineering 版本)

    流程:
    1. RedditFetcher 获取帖子/评论 + Verification
    2. Subagent 并行 → 合并生成影视解说文案 + Verification
    3. TTS 逐段生成配音 + 情绪化停顿 + Verification
    4. 动态字幕生成
    5. B-roll + BGM + 转场 → 视频合成 + Verification
    """

    def __init__(self, config_dict: dict):
        self.config = config_dict
        self.reddit_fetcher = RedditFetcher(config_dict)
        self.output_dir = Path(
            config_dict.get("video", {}).get("output_dir", "./output")
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable[[str, int], None]):
        """设置进度回调函数"""
        self._progress_callback = callback

    def _update_progress(self, step: str, percent: int):
        """更新进度"""
        logger.info(f"[{percent}%] {step}")
        if self._progress_callback:
            self._progress_callback(step, percent)

    def run(
        self,
        reddit_url: str,
        use_story_mode: bool = True,
        enable_broll: bool = True,
        enable_bgm: bool = True,
        dry_run: bool = False,
    ) -> PipelineResult:
        """
        运行完整流水线

        Args:
            reddit_url: Reddit帖子URL或ID
            use_story_mode: 是否使用故事模式
            enable_broll: 是否启用 B-roll
            enable_bgm: 是否启用背景音乐
            dry_run: 只生成文案不合成视频
        """
        result = PipelineResult(success=False)
        session_id = str(uuid.uuid4())[:8]
        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        try:
            # === Step 1: 获取 Reddit 内容 ===
            self._update_progress("正在获取Reddit内容...", 5)
            content = self.reddit_fetcher.fetch_by_url(reddit_url)

            verify = VerificationLoop.verify_reddit_content(content)
            result.verification_log.append(str(verify))
            logger.info(f"\n{verify}")

            if not verify.passed:
                result.error = "Reddit 内容获取失败: " + "; ".join(verify.errors)
                return result

            # === Step 2: Subagent 并行 → 生成影视解说文案 ===
            self._update_progress("正在并行分析内容（评论总结 + 情绪曲线 + B-roll）...", 15)
            script = self._generate_cinematic_script(content, use_story_mode)

            verify = VerificationLoop.verify_script(script)
            result.verification_log.append(str(verify))
            logger.info(f"\n{verify}")

            if not script:
                result.error = "文案生成失败"
                return result
            result.script = script

            # 解析带标注的文案
            parsed_segments = parse_annotated_script(script)

            if dry_run:
                result.success = True
                self._update_progress("Dry run 完成，文案已生成", 100)
                return result

            # === Step 3: TTS 配音 + 情绪化停顿 ===
            self._update_progress("正在生成TTS配音...", 40)
            audio_path, timeline = self._generate_voice_pro(
                parsed_segments, str(session_dir)
            )

            verify = VerificationLoop.verify_tts(audio_path, timeline)
            result.verification_log.append(str(verify))
            logger.info(f"\n{verify}")

            if not audio_path:
                result.error = "TTS 配音生成失败"
                return result
            result.audio_path = audio_path
            result.timeline = timeline

            # === Step 4: 动态字幕 ===
            self._update_progress("正在生成动态字幕...", 60)
            subtitle_path = self._generate_dynamic_subtitle(
                timeline, str(session_dir)
            )

            # === Step 5: 视频合成（B-roll + BGM + 转场） ===
            self._update_progress("正在合成影视解说视频...", 75)
            video_path = self._synthesize_video(
                timeline=timeline,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                session_dir=str(session_dir),
                title=content.thread_title,
                enable_broll=enable_broll,
                enable_bgm=enable_bgm,
            )

            expected_duration = 0
            if timeline:
                expected_duration = max(t.get("end_ms", 0) for t in timeline) / 1000

            verify = VerificationLoop.verify_video(video_path, expected_duration)
            result.verification_log.append(str(verify))
            logger.info(f"\n{verify}")

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

    # --- Step 2: 文案生成（Subagent 并行） ---

    def _generate_cinematic_script(
        self, content: RedditContent, use_story_mode: bool
    ) -> str:
        """
        使用 Subagent 并行 + LLM 生成带标注的影视解说文案

        Subagent 1: 评论总结
        Subagent 2: 情绪曲线
        Subagent 3: B-roll 关键词
        → 合并 → 最终文案（带 [mood:xxx] 和 [broll:xxx] 标注）
        """
        # 并行运行三个 Subagent
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            summary, emotion_curve, broll_keywords = loop.run_until_complete(
                asyncio.gather(
                    _subagent_summarize_comments(
                        content.comments[:10] if use_story_mode else [],
                        self.config
                    ),
                    _subagent_emotion_curve(
                        content.thread_title,
                        content.thread_post or "",
                        self.config
                    ),
                    _subagent_broll_keywords(
                        content.thread_title,
                        content.thread_post or "",
                        self.config
                    ),
                )
            )
            loop.close()
        except Exception as e:
            logger.warning(f"Subagent 并行执行失败: {e}，使用降级方案")
            summary = ""
            emotion_curve = [
                {"paragraph_hint": "开头", "mood": "tense"},
                {"paragraph_hint": "发展", "mood": "emotional"},
                {"paragraph_hint": "结尾", "mood": "upbeat"},
            ]
            broll_keywords = [
                {"paragraph_hint": "开头", "keywords": ["dramatic"]},
                {"paragraph_hint": "发展", "keywords": ["people"]},
                {"paragraph_hint": "结尾", "keywords": ["sunrise"]},
            ]

        logger.info(f"Subagent 结果 - 评论总结: {summary[:80]}...")
        logger.info(f"Subagent 结果 - 情绪曲线: {emotion_curve}")
        logger.info(f"Subagent 结果 - B-roll: {broll_keywords}")

        # 合并三者，生成最终文案
        emotion_str = json.dumps(emotion_curve, ensure_ascii=False)
        broll_str = json.dumps(broll_keywords, ensure_ascii=False)

        comments_text = ""
        if use_story_mode and content.comments:
            comments_text = "\n".join([
                f"- {c['comment_body'][:200]}"
                for c in content.comments[:5]
            ])

        prompt = f"""你是一个影视解说博主。请将下面的内容改写成吸引人的中文解说文案。

帖子标题: {content.thread_title}
帖子内容: {content.thread_post or '无'}
{f"热门评论摘要: {summary}" if summary else ""}
{f"热门评论原文:{chr(10)}{comments_text}" if comments_text else ""}

情绪参考: {emotion_str}
B-roll 关键词参考: {broll_str}

要求:
1. 前3句必须吸引人，像短视频爆款开头
2. 文案长度适合2-4分钟朗读
3. 将评论中的精彩回答自然融入解说
4. 语言生动，口语化，适合朗读
5. 不要出现"Reddit"、"帖子"、"评论"等词
6. 每段之间用 --- 分隔
7. 每段开头必须添加情绪标签 [mood:tense] 或 [mood:emotional] 或 [mood:upbeat] 或 [mood:calm]
8. 每段开头还要添加B-roll标签 [broll:关键词]，关键词用英文
9. 至少分4段

示例格式:
[mood:tense][broll:dark alley night]
你绝对不会相信，这个看似普通的男人，竟然隐藏着一个惊天秘密。
---
[mood:emotional][broll:family dinner]
当他终于鼓起勇气说出真相的那一刻，所有人都沉默了。

请直接输出带标注的解说文案:"""

        script = _call_llm(
            prompt, self.config,
            "你是一个专业的影视解说博主，擅长将网络内容改写成吸引人的短视频文案。严格按照格式要求输出。"
        )
        return script

    # --- Step 3: TTS 配音 + 情绪化停顿 ---

    def _generate_voice_pro(
        self, parsed_segments: List[dict], session_dir: str
    ) -> tuple:
        """
        逐段 TTS + 情绪化停顿 → 合并音频 + 精确时间轴

        Returns:
            (audio_path, timeline): 音频路径和时间轴
        """
        os.makedirs(session_dir, exist_ok=True)

        tts_config = self.config.get("tts", {})
        voice_name = tts_config.get("voice", "zh-CN-XiaoxiaoNeural")

        # 情绪 → 停顿时长映射
        pause_map = {
            "tense": 0.3,
            "emotional": 0.8,
            "upbeat": 0.3,
            "calm": 0.5,
        }

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error("pydub 未安装，无法生成音频")
            return "", []

        from app.services.voice import tts, get_audio_duration_from_file

        combined = AudioSegment.empty()
        timeline = []
        current_ms = 0

        for i, seg in enumerate(parsed_segments):
            text = seg.get("text", "")
            mood = seg.get("mood", "calm")
            broll_kw = seg.get("broll_keywords", [])

            # 生成单段音频
            voice_file = os.path.join(session_dir, f"voice_{i:03d}.mp3")
            try:
                sub_maker = tts(
                    text=text,
                    voice_name=voice_name,
                    voice_rate=1.0,
                    voice_pitch=1.0,
                    voice_file=voice_file,
                    tts_engine="edge_tts",
                )
                if not os.path.exists(voice_file) or os.path.getsize(voice_file) == 0:
                    raise FileNotFoundError(f"TTS 输出文件不存在: {voice_file}")

                segment_audio = AudioSegment.from_file(voice_file)
                duration_ms = len(segment_audio)
            except Exception as e:
                logger.warning(f"TTS 段落 {i} 失败: {e}，使用静音替代")
                duration_ms = int(len(text) * 150)  # 估算
                segment_audio = AudioSegment.silent(duration=duration_ms)

            # 添加到合并音频
            combined += segment_audio

            # 记录时间轴
            timeline.append({
                "text": text,
                "start_ms": current_ms,
                "end_ms": current_ms + duration_ms,
                "mood": mood,
                "broll_keywords": broll_kw,
            })

            current_ms += duration_ms

            # 添加情绪化停顿（非最后一段）
            if i < len(parsed_segments) - 1:
                pause_s = pause_map.get(mood, 0.5)
                pause_ms = int(pause_s * 1000)
                combined += AudioSegment.silent(duration=pause_ms)
                current_ms += pause_ms

        # 导出合并音频
        final_audio = os.path.join(session_dir, "merged_voice.mp3")
        combined.export(final_audio, format="mp3")
        logger.info(f"TTS 音频合并完成: {final_audio} ({current_ms / 1000:.1f}s)")

        return final_audio, timeline

    # --- Step 4: 动态字幕 ---

    def _generate_dynamic_subtitle(
        self, timeline: List[dict], session_dir: str
    ) -> str:
        """生成动态字幕文件（SRT + ASS）"""
        try:
            from app.services.dynamic_subtitle import DynamicSubtitleService

            ds = DynamicSubtitleService(self.config)

            # SRT（兼容性）
            srt_path = os.path.join(session_dir, "subtitle.srt")
            ds.create_styled_srt(timeline, srt_path)

            # ASS（带样式）
            ass_path = os.path.join(session_dir, "subtitle.ass")
            video_config = self.config.get("video", {})
            ds.create_styled_ass(
                timeline, ass_path,
                width=video_config.get("width", 1920),
                height=video_config.get("height", 1080),
            )

            return ass_path  # 优先返回 ASS

        except Exception as e:
            logger.warning(f"动态字幕生成失败: {e}，使用基础 SRT")
            # 降级：使用简单 SRT
            srt_path = os.path.join(session_dir, "subtitle.srt")
            try:
                text = "\n".join(t.get("text", "") for t in timeline)
                create_srt_from_text(text=text, output_path=srt_path, config=self.config)
                return srt_path
            except Exception:
                return ""

    # --- Step 5: 视频合成 ---

    def _synthesize_video(
        self,
        timeline: List[dict],
        audio_path: str,
        subtitle_path: str,
        session_dir: str,
        title: str,
        enable_broll: bool = True,
        enable_bgm: bool = True,
    ) -> str:
        """
        合成最终影视解说视频

        集成: B-roll + 动态字幕 + BGM + 转场
        """
        output_path = os.path.join(session_dir, "final_video.mp4")
        video_config = self.config.get("video", {})
        width = video_config.get("width", 1920)
        height = video_config.get("height", 1080)
        fps = video_config.get("fps", 30)

        try:
            from moviepy import (
                AudioFileClip, ColorClip, CompositeVideoClip,
                CompositeAudioClip, concatenate_videoclips,
            )

            # 计算总时长
            if audio_path and os.path.exists(audio_path):
                audio_clip = AudioFileClip(audio_path)
                total_duration = audio_clip.duration
            else:
                total_duration = max(
                    t.get("end_ms", 0) for t in timeline
                ) / 1000 if timeline else 10.0
                audio_clip = None

            # --- B-roll 视频片段 ---
            broll_clips = []
            if enable_broll:
                broll_clips = self._get_broll_clips(
                    timeline, width, height, total_duration
                )

            # 如果没有 B-roll，用纯色背景
            if not broll_clips:
                bg = ColorClip(
                    size=(width, height), color=(25, 25, 30),
                    duration=total_duration,
                ).with_fps(fps)
                broll_clips = [bg]

            # 合并 B-roll 片段（或使用转场）
            try:
                from app.services.transitions import TransitionService
                ts = TransitionService(self.config)
                video_base = ts.apply_transitions_to_clips(broll_clips)
            except Exception:
                video_base = concatenate_videoclips(broll_clips)

            # 确保总时长匹配音频
            if video_base.duration < total_duration:
                # 延长最后一帧
                padding = ColorClip(
                    size=(width, height), color=(25, 25, 30),
                    duration=total_duration - video_base.duration,
                ).with_fps(fps)
                video_base = concatenate_videoclips([video_base, padding])
            elif video_base.duration > total_duration + 1:
                video_base = video_base.subclipped(0, total_duration)

            video_base = video_base.with_fps(fps)

            # 添加音频
            audio_tracks = []
            if audio_clip:
                audio_tracks.append(audio_clip)

            # --- BGM ---
            if enable_bgm:
                bgm_path = self._get_bgm_track(timeline, session_dir)
                if bgm_path and os.path.exists(bgm_path):
                    try:
                        bgm_clip = AudioFileClip(bgm_path)
                        if bgm_clip.duration > total_duration:
                            bgm_clip = bgm_clip.subclipped(0, total_duration)
                        audio_tracks.append(bgm_clip)
                    except Exception as e:
                        logger.warning(f"BGM 加载失败: {e}")

            # 合并音频
            if audio_tracks:
                if len(audio_tracks) == 1:
                    final_audio = audio_tracks[0]
                else:
                    final_audio = CompositeAudioClip(audio_tracks)
                video_base = video_base.with_audio(final_audio)

            # 输出视频
            video_base.write_videofile(
                output_path,
                fps=fps,
                codec=video_config.get("codec", "libx264"),
                audio_codec=video_config.get("audio_codec", "aac"),
                logger=None,
            )

            # 清理
            video_base.close()
            if audio_clip:
                audio_clip.close()

            logger.info(f"视频生成成功: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"视频合成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

    def _get_broll_clips(
        self, timeline: List[dict], width: int, height: int, total_duration: float
    ) -> list:
        """获取 B-roll 视频片段列表"""
        try:
            from app.services.broll import BRollService
            from moviepy import VideoFileClip, ColorClip

            broll_service = BRollService(self.config)
            clips = []

            for seg in timeline:
                duration_s = (seg.get("end_ms", 0) - seg.get("start_ms", 0)) / 1000
                if duration_s <= 0:
                    duration_s = 3.0

                keywords = seg.get("broll_keywords", [])
                video_path = broll_service.get_broll_for_segment(
                    keywords, duration_s, width, height
                ) if keywords else None

                if video_path and os.path.exists(video_path):
                    try:
                        clip = VideoFileClip(video_path)
                        # 裁剪到需要的时长
                        if clip.duration > duration_s:
                            clip = clip.subclipped(0, duration_s)
                        elif clip.duration < duration_s:
                            # 循环填充
                            loops = int(duration_s / clip.duration) + 1
                            from moviepy import concatenate_videoclips
                            clip = concatenate_videoclips([clip] * loops)
                            clip = clip.subclipped(0, duration_s)
                        # 缩放到目标尺寸
                        clip = clip.resized((width, height))
                        clips.append(clip)
                        continue
                    except Exception as e:
                        logger.warning(f"B-roll 视频加载失败: {e}")

                # 降级：纯色背景
                clips.append(
                    ColorClip(
                        size=(width, height), color=(25, 25, 30),
                        duration=duration_s,
                    )
                )

            return clips

        except ImportError:
            return []
        except Exception as e:
            logger.warning(f"B-roll 获取失败: {e}")
            return []

    def _get_bgm_track(self, timeline: List[dict], session_dir: str) -> Optional[str]:
        """生成 BGM 音轨"""
        try:
            from app.services.bgm import BGMService

            bgm_service = BGMService(self.config)
            total_ms = max(t.get("end_ms", 0) for t in timeline) if timeline else 0
            if total_ms <= 0:
                return None

            bgm_path = os.path.join(session_dir, "bgm_track.mp3")
            return bgm_service.create_bgm_track(timeline, total_ms, bgm_path)

        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"BGM 生成失败: {e}")
            return None


# --- 便捷函数 ---

def run_pipeline(
    reddit_url: str,
    config_dict: dict,
    progress_callback: Optional[Callable] = None,
    enable_broll: bool = True,
    enable_bgm: bool = True,
    dry_run: bool = False,
) -> PipelineResult:
    """便捷函数：运行完整流水线"""
    pipeline = RedditVideoPipeline(config_dict)
    if progress_callback:
        pipeline.set_progress_callback(progress_callback)
    return pipeline.run(
        reddit_url,
        enable_broll=enable_broll,
        enable_bgm=enable_bgm,
        dry_run=dry_run,
    )
