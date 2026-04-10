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
from app.services.llm import generate_script_simple
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
    
    def run(self, reddit_url: str, use_story_mode: bool = True) -> PipelineResult:
        """
        运行完整流水线
        
        Args:
            reddit_url: Reddit帖子URL或ID
            use_story_mode: 是否使用故事模式（帖子作为开头，评论作为内容）
            
        Returns:
            PipelineResult: 处理结果
        """
        result = PipelineResult(success=False)
        session_id = str(uuid.uuid4())[:8]
        
        try:
            # Step 1: 获取Reddit内容
            self._update_progress("正在获取Reddit内容...", 10)
            content = self.reddit_fetcher.fetch_by_url(reddit_url)
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
            script = generate_script_simple(
                prompt=prompt,
                config_dict=self.config,
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
                config_dict=self.config
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
                config_dict=self.config
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
                config_dict=self.config,
                title=content.thread_title
            )
            return video_path or ""
        except Exception as e:
            logger.error(f"视频合成失败: {e}")
            return ""


def run_pipeline(
    reddit_url: str,
    config_dict: dict,
    progress_callback: Optional[Callable] = None
) -> PipelineResult:
    """
    便捷函数：运行完整流水线
    """
    pipeline = RedditVideoPipeline(config_dict)
    if progress_callback:
        pipeline.set_progress_callback(progress_callback)
    return pipeline.run(reddit_url)
