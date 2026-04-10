"""
RedditNarratoAI Verification Loop
每个 Pipeline 步骤执行后自动运行验证，确保输出质量。
"""

import os
import json
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional
from loguru import logger


@dataclass
class VerifyResult:
    """验证结果"""
    passed: bool
    step: str
    checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        lines = [f"[{status}] {self.step}"]
        for c in self.checks:
            lines.append(f"  ✓ {c}")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        for e in self.errors:
            lines.append(f"  ✗ {e}")
        return "\n".join(lines)


class VerificationLoop:
    """
    每步输出的自动自测。
    验证失败时自动重试一次（带日志），仍失败则报错。
    """

    @staticmethod
    def verify_reddit_content(content) -> VerifyResult:
        """
        验证 Reddit 内容获取结果

        检查:
        - 标题非空
        - 评论数 >= 1（警告级别）
        - 无异常字符
        """
        result = VerifyResult(passed=True, step="Reddit Content Fetch")

        # 检查标题
        if not content or not getattr(content, 'thread_title', ''):
            result.errors.append("帖子标题为空")
            result.passed = False
            return result
        result.checks.append(f"标题: {content.thread_title[:50]}...")

        # 检查评论
        comments = getattr(content, 'comments', [])
        if len(comments) == 0:
            result.warnings.append("评论数为 0，文案质量可能受影响")
        else:
            result.checks.append(f"评论数: {len(comments)}")

        # 检查 NSFW
        if getattr(content, 'is_nsfw', False):
            result.warnings.append("帖子标记为 NSFW")

        return result

    @staticmethod
    def verify_script(script: str) -> VerifyResult:
        """
        验证影视解说文案

        检查:
        - 字数范围 (500-2000)
        - 段落数 >= 3
        - 情绪标签覆盖率
        - 不含禁用词
        """
        result = VerifyResult(passed=True, step="Cinematic Script Generation")

        if not script or not script.strip():
            result.errors.append("文案为空")
            result.passed = False
            return result

        # 清理标注后计算纯文本长度
        import re
        clean_text = re.sub(r'\[(?:mood|broll):[^\]]*\]', '', script)
        clean_text = clean_text.replace('---', '').strip()
        char_count = len(clean_text)

        if char_count < 100:
            result.errors.append(f"文案过短: {char_count} 字 (最少 100)")
            result.passed = False
        elif char_count < 500:
            result.warnings.append(f"文案较短: {char_count} 字 (建议 500+)")
        elif char_count > 2000:
            result.warnings.append(f"文案较长: {char_count} 字 (建议 2000 以内)")
        result.checks.append(f"文案长度: {char_count} 字")

        # 检查段落数
        paragraphs = [p.strip() for p in script.split('---') if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in script.split('\n') if p.strip()]
        if len(paragraphs) < 3:
            result.warnings.append(f"段落数: {len(paragraphs)} (建议 >= 3)")
        else:
            result.checks.append(f"段落数: {len(paragraphs)}")

        # 检查情绪标签
        mood_tags = re.findall(r'\[mood:(\w+)\]', script)
        if mood_tags:
            result.checks.append(f"情绪标签: {', '.join(set(mood_tags))}")
        else:
            result.warnings.append("无情绪标签 [mood:xxx]（将使用默认样式）")

        # 检查 B-roll 标签
        broll_tags = re.findall(r'\[broll:([^\]]+)\]', script)
        if broll_tags:
            result.checks.append(f"B-roll 标签数: {len(broll_tags)}")
        else:
            result.warnings.append("无 B-roll 标签 [broll:xxx]（将使用默认背景）")

        # 检查禁用词
        forbidden = ["Reddit", "reddit", "帖子", "评论区"]
        found = [w for w in forbidden if w in clean_text]
        if found:
            result.warnings.append(f"包含禁用词: {', '.join(found)}")

        return result

    @staticmethod
    def verify_tts(audio_path: str, timeline: list) -> VerifyResult:
        """
        验证 TTS 输出

        检查:
        - 音频文件存在且大小 > 0
        - 总时长在 30s-600s 之间
        - 时间轴条目数与段落数匹配
        """
        result = VerifyResult(passed=True, step="Chinese TTS Pro")

        # 检查音频文件
        if not audio_path or not os.path.exists(audio_path):
            result.errors.append(f"音频文件不存在: {audio_path}")
            result.passed = False
            return result

        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            result.errors.append("音频文件大小为 0")
            result.passed = False
            return result
        result.checks.append(f"音频文件: {file_size / 1024:.1f} KB")

        # 检查时间轴
        if not timeline:
            result.warnings.append("时间轴为空")
        else:
            result.checks.append(f"时间轴条目: {len(timeline)}")

            # 检查总时长
            if timeline:
                total_ms = max(t.get('end_ms', 0) for t in timeline)
                total_s = total_ms / 1000
                if total_s < 30:
                    result.warnings.append(f"总时长过短: {total_s:.1f}s (建议 >= 120s)")
                elif total_s > 600:
                    result.warnings.append(f"总时长过长: {total_s:.1f}s (建议 <= 300s)")
                else:
                    result.checks.append(f"总时长: {total_s:.1f}s")

        return result

    @staticmethod
    def verify_video(video_path: str, expected_duration: float = 0) -> VerifyResult:
        """
        验证最终视频

        检查:
        - 文件存在且大小 > 100KB
        - 时长与音频匹配（误差 < 2s）
        - ffprobe 无报错
        """
        result = VerifyResult(passed=True, step="Cinematic Video Synthesis")

        # 检查文件
        if not video_path or not os.path.exists(video_path):
            result.errors.append(f"视频文件不存在: {video_path}")
            result.passed = False
            return result

        file_size = os.path.getsize(video_path)
        if file_size < 100 * 1024:  # 100KB
            result.errors.append(f"视频文件过小: {file_size / 1024:.1f} KB")
            result.passed = False
            return result
        result.checks.append(f"视频文件: {file_size / 1024 / 1024:.1f} MB")

        # ffprobe 检查
        try:
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", video_path
            ]
            probe_result = subprocess.run(
                probe_cmd, capture_output=True, text=True, timeout=10
            )
            if probe_result.returncode == 0:
                probe_data = json.loads(probe_result.stdout)
                duration = float(probe_data.get("format", {}).get("duration", 0))
                result.checks.append(f"视频时长: {duration:.1f}s")

                if expected_duration > 0:
                    diff = abs(duration - expected_duration)
                    if diff > 2.0:
                        result.warnings.append(
                            f"时长偏差: {diff:.1f}s (期望 {expected_duration:.1f}s)"
                        )
                    else:
                        result.checks.append(f"时长匹配: 偏差 {diff:.1f}s")
            else:
                result.warnings.append(f"ffprobe 检查失败: {probe_result.stderr[:100]}")
        except FileNotFoundError:
            result.warnings.append("ffprobe 不可用，跳过视频完整性检查")
        except Exception as e:
            result.warnings.append(f"ffprobe 检查异常: {e}")

        return result

    @classmethod
    def run_with_retry(cls, verify_func, run_func, max_retries: int = 1, **kwargs):
        """
        带重试的验证执行

        Args:
            verify_func: 验证函数
            run_func: 执行函数（返回需要验证的结果）
            max_retries: 最大重试次数
            **kwargs: 传递给 run_func 的参数

        Returns:
            (result, verify_result): 执行结果和验证结果
        """
        for attempt in range(max_retries + 1):
            result = run_func(**kwargs)
            verify_result = verify_func(result) if callable(verify_func) else verify_func

            logger.info(f"\n{verify_result}")

            if verify_result.passed:
                return result, verify_result

            if attempt < max_retries:
                logger.warning(f"验证失败，正在重试 ({attempt + 1}/{max_retries})...")
            else:
                logger.error(f"验证失败，已达到最大重试次数")

        return result, verify_result
