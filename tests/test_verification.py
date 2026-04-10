"""
测试 Verification Loop
"""

import os
import pytest
from unittest.mock import MagicMock
from app.verification import VerificationLoop, VerifyResult


class TestVerifyRedditContent:
    """测试 Reddit 内容验证"""

    def test_valid_content(self):
        content = MagicMock()
        content.thread_title = "Test Title"
        content.comments = [{"comment_body": "Test comment"}]
        content.is_nsfw = False

        result = VerificationLoop.verify_reddit_content(content)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_empty_title(self):
        content = MagicMock()
        content.thread_title = ""

        result = VerificationLoop.verify_reddit_content(content)
        assert result.passed is False
        assert len(result.errors) > 0

    def test_none_content(self):
        result = VerificationLoop.verify_reddit_content(None)
        assert result.passed is False

    def test_no_comments_warning(self):
        content = MagicMock()
        content.thread_title = "Test"
        content.comments = []
        content.is_nsfw = False

        result = VerificationLoop.verify_reddit_content(content)
        assert result.passed is True  # 通过但有警告
        assert len(result.warnings) > 0

    def test_nsfw_warning(self):
        content = MagicMock()
        content.thread_title = "Test"
        content.comments = [{"comment_body": "x"}]
        content.is_nsfw = True

        result = VerificationLoop.verify_reddit_content(content)
        assert result.passed is True
        assert any("NSFW" in w for w in result.warnings)


class TestVerifyScript:
    """测试文案验证"""

    def test_valid_script(self):
        script = """[mood:tense][broll:dark room]
你绝对不会相信这个故事的开头。一个普通的夜晚，一个普通的人，却做出了一个不普通的决定。
---
[mood:emotional][broll:family home]
当真相浮出水面的那一刻，他的眼泪再也忍不住了。这些年的付出和牺牲，终于有了结果。所有的委屈都在这一刻释放。
---
[mood:upbeat][broll:sunrise city]
但命运总是在你意想不到的时候给你惊喜。这个故事的结局，让所有人都露出了笑容。
---
[mood:calm][broll:peaceful lake]
所以啊，生活就是这样，总有一些意想不到的转折在等着我们。你觉得呢？""" + "额外内容" * 50

        result = VerificationLoop.verify_script(script)
        assert result.passed is True
        assert any("情绪标签" in c for c in result.checks)

    def test_empty_script(self):
        result = VerificationLoop.verify_script("")
        assert result.passed is False

    def test_short_script(self):
        result = VerificationLoop.verify_script("太短了")
        assert result.passed is False

    def test_script_without_mood_tags(self):
        script = "这是一个测试文案。" * 30
        result = VerificationLoop.verify_script(script)
        # 通过但有警告
        assert any("情绪标签" in w for w in result.warnings)

    def test_forbidden_words(self):
        script = "这个Reddit帖子的评论区很精彩。" * 30
        result = VerificationLoop.verify_script(script)
        assert any("禁用词" in w for w in result.warnings)


class TestVerifyTTS:
    """测试 TTS 验证"""

    def test_missing_audio(self):
        result = VerificationLoop.verify_tts("/nonexistent/file.mp3", [])
        assert result.passed is False

    def test_empty_timeline_warning(self):
        # 创建临时音频文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"fake audio content")
            tmp_path = f.name

        try:
            result = VerificationLoop.verify_tts(tmp_path, [])
            assert result.passed is True
            assert len(result.warnings) > 0
        finally:
            os.unlink(tmp_path)


class TestVerifyVideo:
    """测试视频验证"""

    def test_missing_video(self):
        result = VerificationLoop.verify_video("/nonexistent/video.mp4")
        assert result.passed is False

    def test_small_video(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"too small")
            tmp_path = f.name

        try:
            result = VerificationLoop.verify_video(tmp_path)
            assert result.passed is False  # 文件太小
        finally:
            os.unlink(tmp_path)


class TestVerifyResult:
    """测试 VerifyResult 格式化"""

    def test_str_pass(self):
        result = VerifyResult(passed=True, step="Test")
        result.checks.append("检查项1")
        text = str(result)
        assert "PASS" in text
        assert "Test" in text

    def test_str_fail(self):
        result = VerifyResult(passed=False, step="Test")
        result.errors.append("错误1")
        text = str(result)
        assert "FAIL" in text
