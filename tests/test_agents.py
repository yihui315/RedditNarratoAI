"""
Agent系统单元测试
测试各Agent的基本逻辑、verify验证、以及Orchestrator编排
使用mock避免真实API调用
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import BaseAgent, AgentResult
from app.agents.material_scout import MaterialScoutAgent
from app.agents.plot_analyzer import PlotAnalyzerAgent
from app.agents.script_writer import ScriptWriterAgent
from app.agents.voice_agent import VoiceAgent
from app.agents.video_editor import VideoEditorAgent
from app.agents.orchestrator import AgentOrchestrator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def base_config():
    """基本配置"""
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
            {"name": "恶霸", "role": "反派", "description": "校园恶霸"},
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
# BaseAgent Tests
# ------------------------------------------------------------------

class ConcreteAgent(BaseAgent):
    """用于测试的具体Agent实现"""
    def __init__(self, config, should_succeed=True):
        super().__init__(config, name="TestAgent")
        self.should_succeed = should_succeed
        self.run_count = 0

    def run(self, input_data):
        self.run_count += 1
        if self.should_succeed:
            return AgentResult(success=True, data={"value": 42})
        return AgentResult(success=False, error="模拟失败")

    def verify(self, result):
        return result.success


class TestBaseAgent:
    def test_execute_success(self, base_config):
        agent = ConcreteAgent(base_config, should_succeed=True)
        result = agent.execute({"key": "value"})
        assert result.success is True
        assert result.data["value"] == 42
        assert result.retries == 1

    def test_execute_retry_on_failure(self, base_config):
        agent = ConcreteAgent(base_config, should_succeed=False)
        result = agent.execute({})
        assert result.success is False
        assert agent.run_count == 2  # max_retries=2

    def test_agent_has_unique_id(self, base_config):
        a1 = ConcreteAgent(base_config)
        a2 = ConcreteAgent(base_config)
        assert a1.agent_id != a2.agent_id

    def test_duration_tracked(self, base_config):
        agent = ConcreteAgent(base_config, should_succeed=True)
        result = agent.execute({})
        assert result.duration_seconds >= 0


# ------------------------------------------------------------------
# PlotAnalyzerAgent Tests
# ------------------------------------------------------------------

class TestPlotAnalyzer:
    def test_verify_requires_summary_and_conflicts(self, base_config):
        agent = PlotAnalyzerAgent(base_config)

        good = AgentResult(success=True, data={
            "analysis": {
                "summary": "一个故事",
                "conflicts": [{"description": "冲突", "intensity": "高"}],
            }
        })
        assert agent.verify(good) is True

        no_summary = AgentResult(success=True, data={
            "analysis": {"summary": "", "conflicts": [{"description": "x"}]}
        })
        assert agent.verify(no_summary) is False

        no_conflicts = AgentResult(success=True, data={
            "analysis": {"summary": "有摘要", "conflicts": []}
        })
        assert agent.verify(no_conflicts) is False

    def test_parse_json_response(self, base_config):
        agent = PlotAnalyzerAgent(base_config)

        # Direct JSON
        assert agent._parse_json_response('{"key": "value"}') == {"key": "value"}

        # JSON in code block
        raw = '```json\n{"key": "value"}\n```'
        assert agent._parse_json_response(raw) == {"key": "value"}

        # JSON embedded in text
        raw = 'Some text {"key": "value"} more text'
        assert agent._parse_json_response(raw) == {"key": "value"}

        # Invalid
        assert agent._parse_json_response("not json at all") == {}

    def test_read_subtitle_file(self, base_config):
        agent = PlotAnalyzerAgent(base_config)

        # Create a test SRT file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\n你好世界\n\n")
            f.write("2\n00:00:04,000 --> 00:00:06,000\n测试字幕\n\n")
            path = f.name

        text = agent._read_subtitle_file(path)
        assert "你好世界" in text
        assert "测试字幕" in text
        assert "-->" not in text
        os.unlink(path)


# ------------------------------------------------------------------
# ScriptWriterAgent Tests
# ------------------------------------------------------------------

class TestScriptWriter:
    def test_verify_length_check(self, base_config):
        agent = ScriptWriterAgent(base_config)

        too_short = AgentResult(
            success=True, data={"script": "太短了"}
        )
        assert agent.verify(too_short) is False

        good_length = AgentResult(
            success=True, data={"script": "a" * 200}
        )
        assert agent.verify(good_length) is True

    def test_run_missing_analysis(self, base_config):
        agent = ScriptWriterAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "缺少剧情分析" in result.error


# ------------------------------------------------------------------
# VoiceAgent Tests
# ------------------------------------------------------------------

class TestVoiceAgent:
    def test_verify_checks_file_and_duration(self, base_config):
        agent = VoiceAgent(base_config)

        no_file = AgentResult(
            success=True, data={"audio_path": "/nonexistent.mp3", "total_duration": 30}
        )
        assert agent.verify(no_file) is False

        too_short = AgentResult(
            success=True, data={"audio_path": __file__, "total_duration": 1}
        )
        assert agent.verify(too_short) is False

    def test_run_missing_script(self, base_config):
        agent = VoiceAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "缺少解说文案" in result.error


# ------------------------------------------------------------------
# VideoEditorAgent Tests
# ------------------------------------------------------------------

class TestVideoEditor:
    def test_build_segments(self, base_config):
        from app.agents.video_editor import VideoEditorAgent

        segments = VideoEditorAgent._build_segments(
            script="第一段\n第二段\n第三段",
            audio_path="/tmp/test.mp3",
            durations=[2.0, 3.0, 1.5],
        )
        assert len(segments) == 3
        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 2.0
        assert segments[1].start_time == 2.0
        assert segments[2].start_time == 5.0

    def test_generate_metadata(self, base_config, sample_analysis):
        from app.agents.video_editor import VideoEditorAgent

        meta = VideoEditorAgent._generate_metadata(
            "测试标题", sample_analysis
        )
        assert "短剧解说" in meta["tags"]
        assert "复仇" in meta["tags"]
        assert meta["title"]

    def test_run_missing_inputs(self, base_config):
        agent = VideoEditorAgent(base_config)
        result = agent.run({})
        assert result.success is False

    def test_verify_checks_file_size(self, base_config):
        agent = VideoEditorAgent(base_config)

        no_file = AgentResult(
            success=True, data={"video_path": "/nonexistent.mp4"}
        )
        assert agent.verify(no_file) is False


# ------------------------------------------------------------------
# MaterialScoutAgent Tests
# ------------------------------------------------------------------

class TestMaterialScout:
    def test_run_requires_keywords_or_urls(self, base_config):
        agent = MaterialScoutAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "keywords" in result.error or "urls" in result.error

    def test_verify_requires_files(self, base_config):
        agent = MaterialScoutAgent(base_config)

        no_materials = AgentResult(
            success=True, data={"materials": []}
        )
        assert agent.verify(no_materials) is False

        # Material with no files
        missing_files = AgentResult(
            success=True,
            data={"materials": [{"subtitle_path": "", "video_path": ""}]},
        )
        assert agent.verify(missing_files) is False

    def test_auth_args_empty_by_default(self, base_config):
        """No auth args when config has no cookie/proxy settings"""
        agent = MaterialScoutAgent(base_config)
        assert agent._build_ytdlp_auth_args() == []

    def test_auth_args_cookies_file(self, base_config):
        """cookies_file adds --cookies flag"""
        base_config["youtube"]["cookies_file"] = "/path/to/cookies.txt"
        agent = MaterialScoutAgent(base_config)
        args = agent._build_ytdlp_auth_args()
        assert "--cookies" in args
        assert "/path/to/cookies.txt" in args

    def test_auth_args_cookies_from_browser(self, base_config):
        """cookies_from_browser adds --cookies-from-browser flag"""
        base_config["youtube"]["cookies_from_browser"] = "edge"
        agent = MaterialScoutAgent(base_config)
        args = agent._build_ytdlp_auth_args()
        assert "--cookies-from-browser" in args
        assert "edge" in args

    def test_auth_args_cookies_file_takes_precedence(self, base_config):
        """cookies_file takes precedence over cookies_from_browser"""
        base_config["youtube"]["cookies_file"] = "/path/to/cookies.txt"
        base_config["youtube"]["cookies_from_browser"] = "edge"
        agent = MaterialScoutAgent(base_config)
        args = agent._build_ytdlp_auth_args()
        assert "--cookies" in args
        assert "--cookies-from-browser" not in args

    def test_auth_args_proxy(self, base_config):
        """proxy adds --proxy flag"""
        base_config["youtube"]["proxy"] = "http://127.0.0.1:7890"
        agent = MaterialScoutAgent(base_config)
        args = agent._build_ytdlp_auth_args()
        assert "--proxy" in args
        assert "http://127.0.0.1:7890" in args

    def test_auth_args_combined(self, base_config):
        """cookies + proxy can be used together"""
        base_config["youtube"]["cookies_from_browser"] = "chrome"
        base_config["youtube"]["proxy"] = "socks5://127.0.0.1:1080"
        agent = MaterialScoutAgent(base_config)
        args = agent._build_ytdlp_auth_args()
        assert "--cookies-from-browser" in args
        assert "chrome" in args
        assert "--proxy" in args
        assert "socks5://127.0.0.1:1080" in args


# ------------------------------------------------------------------
# Orchestrator Tests
# ------------------------------------------------------------------

class TestOrchestrator:
    def test_init_creates_agents(self, base_config):
        orch = AgentOrchestrator(base_config)
        assert orch.material_scout is not None
        assert orch.plot_analyzer is not None
        assert orch.script_writer is not None
        assert orch.voice_agent is not None
        assert orch.video_editor is not None

    def test_run_fails_gracefully_without_keywords(self, base_config):
        """MaterialScout should fail if no keywords/urls provided"""
        orch = AgentOrchestrator(base_config)
        results = orch.run(keywords="", urls=[])
        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["stage"] == "material_scout"
