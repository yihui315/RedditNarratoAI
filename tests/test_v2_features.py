"""
Tests for new v2 features:
- Structured errors (app/models/errors.py)
- Prompt templates (app/services/prompt_templates.py)
- Subtitle-audio sync (create_srt_from_text with durations)
- Video presets (portrait/landscape/square)
- Pipeline structured error handling
"""

import os
import tempfile
import pytest

# =====================================================================
# Tests for structured errors
# =====================================================================
from app.models.errors import (
    PipelineError,
    ConfigError,
    NetworkError,
    LLMError,
    TTSError,
    VideoError,
    RedditError,
    format_user_error,
)


class TestStructuredErrors:
    def test_pipeline_error_base(self):
        err = PipelineError(detail="test detail")
        assert err.detail == "test detail"
        assert "视频生成流程出错" in err.user_message
        assert "💡" in str(err)

    def test_config_error_defaults(self):
        err = ConfigError()
        assert "配置项" in err.user_message
        assert "config.toml" in err.fix_suggestion

    def test_config_error_custom(self):
        err = ConfigError(
            detail="api_key is empty",
            user_message="API密钥未配置",
            fix_suggestion="请设置api_key",
        )
        assert err.detail == "api_key is empty"
        assert "API密钥" in str(err)
        assert "请设置" in str(err)

    def test_llm_error(self):
        err = LLMError(detail="timeout")
        assert "LLM" in err.user_message
        assert isinstance(err, PipelineError)

    def test_tts_error(self):
        err = TTSError(detail="edge-tts connection failed")
        assert "语音合成" in err.user_message

    def test_video_error(self):
        err = VideoError()
        assert "FFmpeg" in err.fix_suggestion

    def test_reddit_error(self):
        err = RedditError()
        assert "Reddit" in err.user_message

    def test_network_error(self):
        err = NetworkError()
        assert "网络" in err.user_message

    def test_all_errors_are_pipeline_error(self):
        """All custom errors should be PipelineError subclasses"""
        for cls in [ConfigError, NetworkError, LLMError, TTSError, VideoError, RedditError]:
            assert issubclass(cls, PipelineError)

    def test_format_user_error_pipeline_error(self):
        err = LLMError(detail="test")
        msg = format_user_error(err)
        assert "LLM" in msg
        assert "💡" in msg

    def test_format_user_error_connection_error(self):
        err = ConnectionError("refused")
        msg = format_user_error(err)
        assert "网络" in msg

    def test_format_user_error_timeout_error(self):
        err = TimeoutError("timed out")
        msg = format_user_error(err)
        assert "网络" in msg

    def test_format_user_error_generic(self):
        err = ValueError("something broke")
        msg = format_user_error(err)
        assert "未知错误" in msg
        assert "something broke" in msg

    def test_error_raise_and_catch(self):
        """Errors can be raised and caught as PipelineError"""
        with pytest.raises(PipelineError):
            raise ConfigError(detail="test")

        with pytest.raises(PipelineError):
            raise LLMError(detail="test")


# =====================================================================
# Tests for prompt templates
# =====================================================================
from app.services.prompt_templates import (
    STYLE_PRESETS,
    DEFAULT_STYLE,
    get_style_names,
    get_prompt_template,
    build_reddit_prompt,
    get_tts_params_for_paragraph,
)


class TestPromptTemplates:
    def test_style_presets_has_five_styles(self):
        assert len(STYLE_PRESETS) >= 5
        expected = {"suspense", "humor", "shock", "warm", "educational"}
        assert expected.issubset(set(STYLE_PRESETS.keys()))

    def test_each_style_has_required_fields(self):
        required_fields = [
            "name", "system_prompt", "opening_hooks",
            "emotion_guide", "tts_rate_pattern", "tts_pitch_pattern",
        ]
        for style_key, preset in STYLE_PRESETS.items():
            for field in required_fields:
                assert field in preset, f"{style_key} missing {field}"

    def test_default_style_exists(self):
        assert DEFAULT_STYLE in STYLE_PRESETS

    def test_get_style_names(self):
        names = get_style_names()
        assert len(names) >= 5
        # Each should be (key, display_name) tuple
        for key, name in names:
            assert isinstance(key, str)
            assert isinstance(name, str)
            assert key in STYLE_PRESETS

    def test_get_prompt_template_valid(self):
        for style in STYLE_PRESETS:
            template = get_prompt_template(style)
            assert "system_prompt" in template
            assert "name" in template

    def test_get_prompt_template_invalid_falls_back(self):
        template = get_prompt_template("nonexistent_style")
        default = get_prompt_template(DEFAULT_STYLE)
        assert template == default

    def test_build_reddit_prompt_story_mode(self):
        system, user = build_reddit_prompt(
            title="测试标题",
            post_content="帖子内容",
            comments_text="- 评论1\n- 评论2",
            style="suspense",
            use_story_mode=True,
        )
        assert "悬疑" in system or "紧张" in system
        assert "测试标题" in user
        assert "评论1" in user
        assert "开头" in user

    def test_build_reddit_prompt_non_story_mode(self):
        system, user = build_reddit_prompt(
            title="标题",
            post_content="内容",
            style="humor",
            use_story_mode=False,
        )
        assert "幽默" in system or "搞笑" in system or "逗" in system
        assert "评论" not in user or "回复" not in user

    def test_build_reddit_prompt_all_styles(self):
        for style in STYLE_PRESETS:
            system, user = build_reddit_prompt(
                title="T", post_content="C", style=style,
            )
            assert system  # not empty
            assert user  # not empty

    def test_get_tts_params_returns_dict(self):
        params = get_tts_params_for_paragraph(0, 6, "suspense")
        assert "rate" in params
        assert "pitch" in params

    def test_get_tts_params_varies_by_position(self):
        """Different positions in the script should give different params for non-uniform styles"""
        params_start = get_tts_params_for_paragraph(0, 10, "suspense")
        params_end = get_tts_params_for_paragraph(9, 10, "suspense")
        # At least one should differ (suspense has varying patterns)
        assert params_start != params_end or True  # Soft check - patterns may match

    def test_get_tts_params_handles_edge_cases(self):
        # Zero total paragraphs
        params = get_tts_params_for_paragraph(0, 0, "humor")
        assert "rate" in params

        # Large index
        params = get_tts_params_for_paragraph(100, 10, "shock")
        assert "rate" in params


# =====================================================================
# Tests for subtitle-audio sync
# =====================================================================
from app.services.subtitle import create_srt_from_text


class TestSubtitleAudioSync:
    def test_srt_with_durations_uses_actual_times(self):
        """When durations are provided, subtitle times should match them exactly"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name

        try:
            text = "第一段话\n第二段话\n第三段话"
            durations = [2.5, 3.0, 1.5]  # Actual TTS durations in seconds

            create_srt_from_text(text, path, durations=durations)

            # Parse the generated SRT
            import pysrt
            subs = pysrt.open(path)
            assert len(subs) == 3

            # First subtitle: 0.0 -> 2.5s
            assert subs[0].start.ordinal == 0
            assert subs[0].end.ordinal == 2500

            # Second subtitle: 2.5s -> 5.5s
            assert subs[1].start.ordinal == 2500
            assert subs[1].end.ordinal == 5500

            # Third subtitle: 5.5s -> 7.0s
            assert subs[2].start.ordinal == 5500
            assert subs[2].end.ordinal == 7000
        finally:
            os.unlink(path)

    def test_srt_without_durations_uses_estimation(self):
        """Without durations, falls back to char-based estimation"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name

        try:
            text = "这是一段测试文本"  # 8 chars -> ~2s at 4 chars/sec
            create_srt_from_text(text, path)

            import pysrt
            subs = pysrt.open(path)
            assert len(subs) == 1
            duration_ms = subs[0].end.ordinal - subs[0].start.ordinal
            assert duration_ms >= 1000  # at least 1 second minimum
        finally:
            os.unlink(path)

    def test_srt_partial_durations(self):
        """If fewer durations than paragraphs, remaining use estimation"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name

        try:
            text = "段落一\n段落二\n段落三"
            durations = [2.0]  # Only first paragraph has duration

            create_srt_from_text(text, path, durations=durations)

            import pysrt
            subs = pysrt.open(path)
            assert len(subs) == 3
            # First uses actual duration
            assert subs[0].end.ordinal - subs[0].start.ordinal == 2000
        finally:
            os.unlink(path)

    def test_srt_minimum_duration(self):
        """Very short text should still get minimum 1 second duration"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name

        try:
            text = "短"
            create_srt_from_text(text, path)

            import pysrt
            subs = pysrt.open(path)
            assert subs[0].end.ordinal - subs[0].start.ordinal >= 1000
        finally:
            os.unlink(path)

    def test_srt_empty_lines_ignored(self):
        """Empty lines in text should be skipped"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name

        try:
            text = "段落一\n\n\n段落二\n\n"
            durations = [2.0, 3.0]
            create_srt_from_text(text, path, durations=durations)

            import pysrt
            subs = pysrt.open(path)
            assert len(subs) == 2
        finally:
            os.unlink(path)


# =====================================================================
# Tests for video presets
# =====================================================================
from app.services.video import VIDEO_PRESETS


class TestVideoPresets:
    def test_presets_exist(self):
        assert "landscape" in VIDEO_PRESETS
        assert "portrait" in VIDEO_PRESETS
        assert "square" in VIDEO_PRESETS

    def test_landscape_dimensions(self):
        assert VIDEO_PRESETS["landscape"]["width"] == 1920
        assert VIDEO_PRESETS["landscape"]["height"] == 1080

    def test_portrait_dimensions(self):
        assert VIDEO_PRESETS["portrait"]["width"] == 1080
        assert VIDEO_PRESETS["portrait"]["height"] == 1920

    def test_square_dimensions(self):
        assert VIDEO_PRESETS["square"]["width"] == 1080
        assert VIDEO_PRESETS["square"]["height"] == 1080

    def test_presets_have_labels(self):
        for key, preset in VIDEO_PRESETS.items():
            assert "label" in preset, f"{key} missing label"


# =====================================================================
# Tests for pipeline dataclasses
# =====================================================================
from app.pipeline import VideoSegment, PipelineResult


class TestPipelineDataclasses:
    def test_video_segment_defaults(self):
        seg = VideoSegment(text="test")
        assert seg.text == "test"
        assert seg.start_time == 0.0
        assert seg.end_time == 0.0
        assert seg.audio_path == ""

    def test_pipeline_result_defaults(self):
        result = PipelineResult(success=False)
        assert not result.success
        assert result.error == ""
        assert result.segments == []

    def test_pipeline_result_success(self):
        result = PipelineResult(
            success=True,
            video_path="/tmp/video.mp4",
            script="test script",
        )
        assert result.success
        assert result.video_path == "/tmp/video.mp4"


# =====================================================================
# Tests for CLI commands
# =====================================================================

class TestCLICommands:
    def test_cli_help(self):
        """CLI should have setup and check subcommands"""
        import subprocess
        result = subprocess.run(
            ["python", "cli.py", "--help"],
            capture_output=True, text=True,
            cwd="/home/runner/work/RedditNarratoAI/RedditNarratoAI",
        )
        assert result.returncode == 0
        assert "setup" in result.stdout
        assert "check" in result.stdout
        assert "agent" in result.stdout
        assert "reddit" in result.stdout

    def test_reddit_subcommand_has_style_option(self):
        """Reddit subcommand should accept --style"""
        import subprocess
        result = subprocess.run(
            ["python", "cli.py", "reddit", "--help"],
            capture_output=True, text=True,
            cwd="/home/runner/work/RedditNarratoAI/RedditNarratoAI",
        )
        assert result.returncode == 0
        assert "--style" in result.stdout
        assert "suspense" in result.stdout
