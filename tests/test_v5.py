"""
RedditNarratoAI v5.0 smoke tests — verify all critical imports resolve correctly.
These tests should pass after all P0 fixes are applied.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestImports:
    """Test that all required modules can be imported without errors."""

    def test_config_import(self):
        """app.config package must be importable and re-export config."""
        from app.config import config
        assert config is not None

    def test_models_schema_re_export(self):
        """app.models must re-export VideoAspect and SubtitlePosition."""
        from app.models import VideoAspect, SubtitlePosition
        assert hasattr(VideoAspect, "value")
        assert hasattr(SubtitlePosition, "value")

    def test_llm_generate_script_simple(self):
        """generate_script_simple must exist in llm module."""
        from app.services.llm import generate_script_simple
        assert callable(generate_script_simple)

    def test_voice_generate_voice(self):
        """generate_voice must exist in voice module."""
        from app.services.voice import generate_voice
        assert callable(generate_voice)

    def test_subtitle_create_srt_from_text(self):
        """create_srt_from_text must exist in subtitle module."""
        from app.services.subtitle import create_srt_from_text
        assert callable(create_srt_from_text)

    def test_video_create_video_from_segments(self):
        """create_video_from_segments must exist in video module."""
        from app.services.video import create_video_from_segments
        assert callable(create_video_from_segments)

    def test_reddit_fetcher_import(self):
        """RedditFetcher must be importable."""
        from app.services.reddit import RedditFetcher, RedditContent
        assert RedditFetcher is not None
        assert RedditContent is not None

    def test_pipeline_import(self):
        """RedditVideoPipeline must be importable."""
        from app.pipeline import RedditVideoPipeline
        assert RedditVideoPipeline is not None

    def test_config_loader_whisper_safe(self):
        """config.get('whisper') must not raise AttributeError."""
        from app.config_loader import config
        result = config.get("whisper", {})
        # Should return a dict, not raise AttributeError
        assert isinstance(result, (dict, type(None)))


class TestSrtGeneration:
    """Test create_srt_from_text output."""

    def test_srt_from_text_basic(self):
        from app.services.subtitle import create_srt_from_text
        text = "这是第一句。这是第二句。"
        result = create_srt_from_text(text)
        # Should return string containing SRT format
        assert isinstance(result, str)
        assert "-->" in result
        assert "1\n" in result

    def test_srt_from_text_to_file(self):
        import tempfile
        from app.services.subtitle import create_srt_from_text
        text = "Hello world. 你好世界。"
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
            path = f.name
        try:
            result = create_srt_from_text(text, output_path=path)
            assert result == path
            with open(path) as f:
                content = f.read()
            assert "-->" in content
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestGoogleGenAiMigration:
    """Test google.genai migration with fallback."""

    def test_llm_google_genai_fallback(self):
        """llm.py should import google.genai with fallback to google.generativeai."""
        # Should not raise ImportError at module level
        from app.services import llm as llm_module
        assert hasattr(llm_module, "gemini")

    def test_subtitle_google_genai_fallback(self):
        """subtitle.py should import google.genai with fallback."""
        from app.services import subtitle as subtitle_module
        # Module should have genai attribute
        assert hasattr(subtitle_module, "genai")
