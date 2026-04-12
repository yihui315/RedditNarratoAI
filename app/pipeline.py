"""
RedditNarratoAI 核心流水线
Reddit帖子 → AI文案改写 → TTS配音 → 字幕 → 视频剪辑

v2 改进:
- 字幕与配音精确同步（使用TTS实际时长）
- Prompt模板库（多风格预设）
- 结构化错误提示（用户友好的中文提示 + 修复建议）
- LLM调用超时 + tenacity重试
"""

import os
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from pathlib import Path
from loguru import logger

from app.config import config
from app.services.reddit import RedditFetcher, RedditContent
from app.services.voice import generate_voice
from app.services.subtitle import create_srt_from_text
from app.services.prompt_templates import (
    build_reddit_prompt,
    DEFAULT_STYLE,
    get_style_names,
)
from app.models.errors import (
    PipelineError,
    ConfigError,
    LLMError,
    TTSError,
    VideoError,
    RedditError,
    format_user_error,
)


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
    2. LLM 改写为解说文案（Prompt模板库）
    3. TTS 生成配音
    4. 字幕生成（精确同步TTS时长）
    5. 视频剪辑合成
    """

    def __init__(self, config_dict: dict):
        self.config = config_dict
        self.reddit_fetcher = RedditFetcher(config_dict)
        self.output_dir = Path(config_dict.get("app", {}).get("output_dir", "./output"))
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
        style: str = DEFAULT_STYLE,
    ) -> PipelineResult:
        """
        运行完整流水线

        Args:
            reddit_url: Reddit帖子URL或ID
            use_story_mode: 是否使用故事模式
            style: 文案风格预设 (suspense/humor/shock/warm/educational)

        Returns:
            PipelineResult: 处理结果
        """
        result = PipelineResult(success=False)
        session_id = str(uuid.uuid4())[:8]

        try:
            # Step 1: 获取Reddit内容
            self._update_progress("正在获取Reddit内容...", 5)
            content = self._fetch_reddit(reddit_url)
            logger.info(f"获取到帖子: {content.thread_title}")
            logger.info(f"评论数: {len(content.comments)}")

            # Step 2: 生成解说文案
            self._update_progress("正在生成AI解说文案...", 20)
            script = self._generate_script(content, use_story_mode, style)
            result.script = script

            # Step 3: 生成配音
            self._update_progress("正在生成TTS配音...", 40)
            audio_path, durations = self._generate_voice(script, session_id)
            result.audio_path = audio_path

            # Step 4: 用TTS真实时长生成精确字幕
            self._update_progress("正在生成精确字幕...", 65)
            subtitle_path, segments = self._generate_subtitle_synced(
                script, durations, session_id
            )
            result.segments = segments

            # Step 5: 合成视频
            self._update_progress("正在合成视频...", 80)
            video_path = self._create_video(
                segments=segments,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                session_id=session_id,
                content=content,
            )

            if video_path and os.path.exists(video_path):
                result.success = True
                result.video_path = video_path
                self._update_progress("视频生成完成!", 100)
            else:
                result.error = str(VideoError(detail="output file missing"))

        except PipelineError as e:
            logger.error(f"流水线错误: {e.detail}")
            result.error = str(e)
        except Exception as e:
            logger.exception("流水线执行出错")
            result.error = format_user_error(e)

        return result

    # ------------------------------------------------------------------
    # Step 1: Fetch Reddit
    # ------------------------------------------------------------------

    def _fetch_reddit(self, reddit_url: str) -> RedditContent:
        """获取Reddit内容，失败时抛出结构化错误"""
        try:
            content = self.reddit_fetcher.fetch_by_url(reddit_url)
        except Exception as e:
            raise RedditError(
                detail=str(e),
                user_message="无法获取Reddit内容",
                fix_suggestion="请检查URL是否正确、Reddit API凭据是否有效、网络是否可访问Reddit",
            ) from e

        if not content:
            raise RedditError(
                detail=f"fetch returned None for {reddit_url}",
                user_message="无法获取Reddit内容",
                fix_suggestion="请检查URL格式是否正确，或帖子是否已被删除",
            )
        return content

    # ------------------------------------------------------------------
    # Step 2: Generate Script
    # ------------------------------------------------------------------

    def _generate_script(
        self,
        content: RedditContent,
        use_story_mode: bool,
        style: str,
    ) -> str:
        """使用Prompt模板库 + tenacity重试生成解说文案"""
        comments_text = ""
        if use_story_mode and content.comments:
            comments_text = "\n".join(
                f"- {c['comment_body'][:200]}"
                for c in content.comments[:5]
            )

        system_prompt, user_prompt = build_reddit_prompt(
            title=content.thread_title,
            post_content=content.thread_post or "",
            comments_text=comments_text,
            style=style,
            use_story_mode=use_story_mode,
        )

        try:
            script = self._call_llm(user_prompt, system_prompt)
        except Exception as e:
            raise LLMError(
                detail=str(e),
                user_message="AI文案生成失败",
                fix_suggestion="请确认LLM服务运行中（Ollama: ollama serve），API密钥有效",
            ) from e

        if not script or not script.strip():
            raise LLMError(
                detail="LLM returned empty response",
                user_message="AI返回空文案",
                fix_suggestion="请稍后重试，或更换模型/提供商",
            )

        return script.strip()

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用LLM，带超时和重试"""
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        llm_config = self.config.get("llm", {})
        provider = llm_config.get("provider", "openai")
        api_base = llm_config.get("api_base", "http://localhost:11434/v1")
        api_key = llm_config.get("api_key", "not-needed")
        model = llm_config.get("model", "deepseek-r1:32b")
        max_tokens = llm_config.get("max_tokens", 4096)
        temperature = llm_config.get("temperature", 0.7)

        if not api_key:
            raise ConfigError(
                detail="llm.api_key is empty",
                user_message="LLM API密钥未配置",
                fix_suggestion="请在config.toml的[llm]部分设置api_key",
            )

        from openai import OpenAI

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
            reraise=True,
        )
        def _do_call():
            client = OpenAI(
                api_key=api_key,
                base_url=api_base,
                timeout=60.0,
            )
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
            return response.choices[0].message.content

        return _do_call()

    # ------------------------------------------------------------------
    # Step 3: Generate Voice
    # ------------------------------------------------------------------

    def _generate_voice(self, script: str, session_id: str) -> tuple:
        """
        生成TTS配音，返回 (audio_path, durations)

        durations 列表精确记录每个段落的实际音频时长（秒）
        """
        try:
            audio_path, durations = generate_voice(
                text=script,
                output_dir=str(self.output_dir / session_id),
                config=self.config,
            )
        except Exception as e:
            raise TTSError(
                detail=str(e),
                user_message="TTS配音生成失败",
                fix_suggestion="请检查TTS引擎配置，确认Edge TTS服务可用（需要网络连接）",
            ) from e

        if not audio_path:
            raise TTSError(
                detail="generate_voice returned empty path",
                user_message="配音音频文件未生成",
                fix_suggestion="请检查磁盘空间和TTS配置",
            )

        return audio_path, durations

    # ------------------------------------------------------------------
    # Step 4: Generate Subtitle (synced with TTS)
    # ------------------------------------------------------------------

    def _generate_subtitle_synced(
        self,
        script: str,
        durations: list,
        session_id: str,
    ) -> tuple:
        """
        使用TTS实际时长生成精确同步的字幕 + VideoSegment列表
        """
        subtitle_path = str(self.output_dir / session_id / "subtitle.srt")

        try:
            create_srt_from_text(
                text=script,
                output_path=subtitle_path,
                config=self.config,
                durations=durations,
            )
        except Exception as e:
            logger.error(f"字幕生成失败: {e}")
            subtitle_path = ""

        # Build segments using actual durations
        texts = [t.strip() for t in script.split("\n") if t.strip()]
        segments = []
        current_time = 0.0
        for i, text in enumerate(texts):
            dur = durations[i] if i < len(durations) else 3.0
            segments.append(
                VideoSegment(
                    text=text,
                    start_time=current_time,
                    end_time=current_time + dur,
                )
            )
            current_time += dur

        return subtitle_path, segments

    # ------------------------------------------------------------------
    # Step 5: Create Video
    # ------------------------------------------------------------------

    def _create_video(
        self,
        segments: List[VideoSegment],
        audio_path: str,
        subtitle_path: str,
        session_id: str,
        content: RedditContent,
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
                title=content.thread_title,
            )
            return video_path or ""
        except Exception as e:
            raise VideoError(
                detail=str(e),
                user_message="视频合成失败",
                fix_suggestion="请确认FFmpeg已安装，磁盘空间充足",
            ) from e


def run_pipeline(
    reddit_url: str,
    config_dict: dict,
    progress_callback: Optional[Callable] = None,
    style: str = DEFAULT_STYLE,
) -> PipelineResult:
    """
    便捷函数：运行完整流水线
    """
    pipeline = RedditVideoPipeline(config_dict)
    if progress_callback:
        pipeline.set_progress_callback(progress_callback)
    return pipeline.run(reddit_url, style=style)
