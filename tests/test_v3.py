"""
v3.0 Agent系统测试
测试新增的4个Agent (VideoGen, BrollMatcher, SEO, Publish)
+ 升级后的9-Agent Orchestrator
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import AgentResult
from app.agents.video_gen import VideoGenAgent
from app.agents.broll_matcher import BrollMatcherAgent
from app.agents.seo_agent import SEOAgent
from app.agents.publish_agent import PublishAgent
from app.agents.orchestrator import AgentOrchestrator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def base_config():
    """基本配置（v3.0）"""
    return {
        "agents": {
            "work_dir": tempfile.mkdtemp(),
            "max_retries": 2,
        },
        "youtube": {
            "max_results": 3,
            "min_views": 100,
            "subtitle_language": "zh",
        },
        "tts": {
            "provider": "edge",
            "voice": "zh-CN-XiaoxiaoNeural",
        },
        "video": {
            "output_dir": tempfile.mkdtemp(),
        },
        "llm": {},
        "video_gen": {
            "mode": "moviepy",
        },
        "pexels": {
            "api_key": "",
            "max_clips": 3,
        },
        "publish": {
            "auto_publish": False,
            "platforms": ["tiktok", "youtube_shorts"],
        },
    }


@pytest.fixture
def sample_analysis():
    """样例剧情分析结果"""
    return {
        "title": "测试短剧",
        "genre": "复仇",
        "summary": "一个被欺负的女孩逆袭复仇的故事",
        "characters": [
            {"name": "小美", "role": "主角", "description": "被欺负的女孩"},
        ],
        "conflicts": [
            {"description": "小美被恶霸欺负", "intensity": "高"},
        ],
        "reversals": ["小美获得超能力"],
        "emotional_peaks": [
            {"moment": "小美反击", "emotion": "震惊"},
        ],
        "hook_points": ["被欺负的那一刻"],
    }


# ------------------------------------------------------------------
# VideoGenAgent Tests
# ------------------------------------------------------------------

class TestVideoGenAgent:
    def test_init_default_moviepy(self, base_config):
        agent = VideoGenAgent(base_config)
        assert agent.mode == "moviepy"

    def test_init_auto_detect_kling(self, base_config):
        base_config["video_gen"] = {"kling_api_key": "test-key"}
        agent = VideoGenAgent(base_config)
        assert agent.mode == "kling"

    def test_init_auto_detect_runway(self, base_config):
        base_config["video_gen"] = {"runway_api_key": "test-key"}
        agent = VideoGenAgent(base_config)
        assert agent.mode == "runway"

    def test_init_explicit_mode(self, base_config):
        base_config["video_gen"] = {"mode": "runway", "kling_api_key": "test"}
        agent = VideoGenAgent(base_config)
        assert agent.mode == "runway"

    def test_run_moviepy_passthrough(self, base_config):
        agent = VideoGenAgent(base_config)
        result = agent.run({"script": "测试脚本", "session_id": "test"})
        assert result.success is True
        assert result.data["mode"] == "moviepy"

    def test_run_missing_script(self, base_config):
        agent = VideoGenAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "缺少脚本" in result.error

    def test_verify_moviepy_always_passes(self, base_config):
        agent = VideoGenAgent(base_config)
        result = AgentResult(
            success=True,
            data={"mode": "moviepy", "video_clips": []},
        )
        assert agent.verify(result) is True

    def test_verify_ai_mode_needs_files(self, base_config):
        agent = VideoGenAgent(base_config)
        result = AgentResult(
            success=True,
            data={"mode": "kling", "video_clips": []},
        )
        assert agent.verify(result) is False


# ------------------------------------------------------------------
# BrollMatcherAgent Tests
# ------------------------------------------------------------------

class TestBrollMatcherAgent:
    def test_no_api_key_skips(self, base_config):
        agent = BrollMatcherAgent(base_config)
        result = agent.run({"script": "测试", "analysis": {}, "session_id": "test"})
        assert result.success is True
        assert result.data["broll_clips"] == []

    def test_extract_keywords(self, base_config, sample_analysis):
        agent = BrollMatcherAgent(base_config)
        keywords = agent._extract_keywords("城市里的一个夜晚", sample_analysis)
        assert "复仇" in keywords
        assert "城市" in keywords
        assert "夜晚" in keywords

    def test_extract_keywords_from_emotions(self, base_config, sample_analysis):
        agent = BrollMatcherAgent(base_config)
        keywords = agent._extract_keywords("一段普通文案", sample_analysis)
        assert "震惊" in keywords

    def test_verify_always_passes(self, base_config):
        """B-roll is optional, so verify always passes when success=True"""
        agent = BrollMatcherAgent(base_config)
        result = AgentResult(success=True, data={"broll_clips": []})
        assert agent.verify(result) is True

    def test_pick_best_file_prefers_720p(self, base_config):
        agent = BrollMatcherAgent(base_config)
        files = [
            {"height": 1080, "link": "https://example.com/1080p.mp4"},
            {"height": 720, "link": "https://example.com/720p.mp4"},
            {"height": 480, "link": "https://example.com/480p.mp4"},
        ]
        result = agent._pick_best_file(files)
        assert "720p" in result


# ------------------------------------------------------------------
# SEOAgent Tests
# ------------------------------------------------------------------

class TestSEOAgent:
    def test_run_missing_input(self, base_config):
        agent = SEOAgent(base_config)
        result = agent.run({})
        assert result.success is False

    def test_fallback_seo(self, base_config, sample_analysis):
        seo = SEOAgent._fallback_seo("测试标题", "复仇", sample_analysis)
        assert "短剧解说" in seo["tags"]
        assert seo["seo_title"]
        assert len(seo["tags"]) >= 5

    def test_verify_needs_title_and_tags(self, base_config):
        agent = SEOAgent(base_config)

        good = AgentResult(
            success=True,
            data={"seo": {"seo_title": "标题", "tags": ["a", "b", "c"]}},
        )
        assert agent.verify(good) is True

        no_title = AgentResult(
            success=True,
            data={"seo": {"seo_title": "", "tags": ["a", "b", "c"]}},
        )
        assert agent.verify(no_title) is False

        few_tags = AgentResult(
            success=True,
            data={"seo": {"seo_title": "标题", "tags": ["a"]}},
        )
        assert agent.verify(few_tags) is False

    def test_parse_json(self, base_config):
        agent = SEOAgent(base_config)

        # Direct JSON
        assert agent._parse_json('{"key": "val"}') == {"key": "val"}

        # JSON in code block
        raw = '```json\n{"key": "val"}\n```'
        assert agent._parse_json(raw) == {"key": "val"}

        # Invalid
        assert agent._parse_json("not json") == {}

    def test_run_with_llm_failure_uses_fallback(self, base_config, sample_analysis):
        """When LLM fails, SEO agent should use fallback"""
        agent = SEOAgent(base_config)
        with patch("app.agents.seo_agent.generate_response_from_config", side_effect=Exception("LLM down")):
            result = agent.run({
                "title": "测试",
                "analysis": sample_analysis,
            })
            # Should still succeed with fallback
            assert result.success is True
            assert result.data.get("fallback") is True


# ------------------------------------------------------------------
# PublishAgent Tests
# ------------------------------------------------------------------

class TestPublishAgent:
    def test_init_defaults(self, base_config):
        agent = PublishAgent(base_config)
        assert agent.auto_publish is False

    def test_run_missing_video(self, base_config):
        agent = PublishAgent(base_config)
        result = agent.run({"video_path": "/nonexistent.mp4"})
        assert result.success is False

    def test_run_manual_mode(self, base_config):
        """When auto_publish is False, should prepare package"""
        agent = PublishAgent(base_config)

        # Create a temp video file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video content")
            video_path = f.name

        try:
            result = agent.run({
                "video_path": video_path,
                "seo": {"seo_title": "test"},
                "session_id": "test",
            })
            assert result.success is True
            assert result.data["auto_publish"] is False
            assert result.data["package_path"]
        finally:
            os.unlink(video_path)

    def test_verify_manual_mode(self, base_config):
        agent = PublishAgent(base_config)
        result = AgentResult(
            success=True,
            data={"auto_publish": False, "package_path": "/tmp/test.json"},
        )
        assert agent.verify(result) is True

        no_package = AgentResult(
            success=True,
            data={"auto_publish": False, "package_path": ""},
        )
        assert agent.verify(no_package) is False


# ------------------------------------------------------------------
# Orchestrator v3.0 Tests
# ------------------------------------------------------------------

class TestOrchestratorV3:
    def test_init_creates_all_9_agents(self, base_config):
        orch = AgentOrchestrator(base_config)
        assert orch.material_scout is not None
        assert orch.plot_analyzer is not None
        assert orch.script_writer is not None
        assert orch.voice_agent is not None
        assert orch.video_editor is not None
        # v3.0 new agents
        assert orch.video_gen is not None
        assert orch.broll_matcher is not None
        assert orch.seo_agent is not None
        assert orch.publish_agent is not None

    def test_run_fails_gracefully_without_keywords(self, base_config):
        """MaterialScout should fail if no keywords/urls provided"""
        orch = AgentOrchestrator(base_config)
        results = orch.run(keywords="", urls=[])
        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["stage"] == "material_scout"

    def test_progress_callback(self, base_config):
        """Progress callback should be called"""
        orch = AgentOrchestrator(base_config)
        calls = []
        orch.set_progress_callback(lambda a, p, m: calls.append((a, p, m)))
        orch.run(keywords="", urls=[])
        assert len(calls) > 0
        assert calls[0][0] == "MaterialScout"

    def test_iteration_data_saved(self, base_config):
        """Iteration data should be saved after run"""
        orch = AgentOrchestrator(base_config)
        orch.run(keywords="", urls=[])
        # Check iteration directory has files
        import glob
        files = glob.glob(str(orch._iteration_dir / "iteration_*.json"))
        assert len(files) > 0


# ------------------------------------------------------------------
# Prompt files existence tests
# ------------------------------------------------------------------

class TestPromptFiles:
    def test_script_writer_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "v3_script_writer_prompt.txt",
        )
        assert os.path.exists(path)

    def test_reddit_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "v3_reddit_prompt.txt",
        )
        assert os.path.exists(path)

    def test_iteration_schema_valid_json(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "self_iteration_schema.json",
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        assert schema["title"]
        assert "video_id" in schema["properties"]


# ------------------------------------------------------------------
# Docker files existence tests
# ------------------------------------------------------------------

class TestDockerFiles:
    def test_dockerfile_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "Dockerfile",
        )
        assert os.path.exists(path)

    def test_docker_compose_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docker-compose.yml",
        )
        assert os.path.exists(path)
