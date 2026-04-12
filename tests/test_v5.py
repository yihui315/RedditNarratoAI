"""
v5.0 Agent系统测试
测试新增的4个Agent (CharacterGen, StoryboardBreaker, DubbingAgent, VisualAsset)
+ 升级后的18-Agent Orchestrator (双模式: narration vs drama)
+ 跨会话记忆持久化
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import AgentResult
from app.agents.character_gen import CharacterGenAgent
from app.agents.storyboard_breaker import StoryboardBreakerAgent
from app.agents.dubbing_agent import DubbingAgent
from app.agents.visual_asset import VisualAssetAgent
from app.agents.orchestrator import AgentOrchestrator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def base_config():
    """基本配置（v5.0）"""
    tmpdir = tempfile.mkdtemp()
    return {
        "agents": {
            "work_dir": tmpdir,
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
            "rate": "+0%",
        },
        "video": {
            "output_dir": tmpdir,
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
        "dubbing": {
            "enabled": True,
            "gpt_sovits_api": "",
        },
        "visual_asset": {
            "minimax_api_key": "",
            "vidu_api_key": "",
        },
        "app": {
            "root_dir": tmpdir,
        },
    }


@pytest.fixture
def sample_characters():
    """样例角色列表"""
    return [
        {
            "name": "小美",
            "role": "protagonist",
            "appearance": "年轻女性，长发，眼神坚毅",
            "voice_id": "warm_female",
            "personality": "隐忍、善良、关键时刻爆发",
            "age_range": "20-25",
        },
        {
            "name": "渣男",
            "role": "antagonist",
            "appearance": "帅气男性，西装，表情阴险",
            "voice_id": "cold_male",
            "personality": "傲慢、虚伪、两面三刀",
            "age_range": "25-30",
        },
    ]


# ------------------------------------------------------------------
# CharacterGenAgent Tests
# ------------------------------------------------------------------

class TestCharacterGenAgent:
    def test_run_missing_input(self, base_config):
        agent = CharacterGenAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "主题" in result.error or "theme" in result.error

    def test_run_with_theme_fallback(self, base_config):
        """LLM不可用时，使用默认角色模板"""
        agent = CharacterGenAgent(base_config)
        result = agent.run({"theme": "复仇短剧 女主被渣男抛弃"})
        assert result.success is True
        characters = result.data.get("characters", [])
        assert len(characters) >= 2
        assert characters[0]["role"] == "protagonist"
        assert characters[1]["role"] == "antagonist"
        assert result.data.get("fallback") is True

    def test_run_with_script(self, base_config):
        """也可用script作为输入"""
        agent = CharacterGenAgent(base_config)
        result = agent.run({"script": "小美被渣男抛弃后，决定开始新的人生"})
        assert result.success is True
        assert len(result.data.get("characters", [])) >= 1

    def test_verify_requires_name_and_role(self, base_config):
        agent = CharacterGenAgent(base_config)

        good = AgentResult(
            success=True,
            data={"characters": [
                {"name": "小美", "role": "protagonist"},
                {"name": "渣男", "role": "antagonist"},
            ]},
        )
        assert agent.verify(good) is True

        no_name = AgentResult(
            success=True,
            data={"characters": [{"name": "", "role": "protagonist"}]},
        )
        assert agent.verify(no_name) is False

        empty = AgentResult(success=True, data={"characters": []})
        assert agent.verify(empty) is False

    def test_parse_characters_json(self, base_config):
        agent = CharacterGenAgent(base_config)

        # 直接JSON
        raw = '[{"name": "A", "role": "protagonist"}]'
        assert agent._parse_characters(raw) == [{"name": "A", "role": "protagonist"}]

        # 代码块
        raw = '```json\n[{"name": "B", "role": "antagonist"}]\n```'
        assert agent._parse_characters(raw) == [{"name": "B", "role": "antagonist"}]

        # 内嵌
        raw = 'Here: [{"name": "C", "role": "supporting"}] done'
        assert agent._parse_characters(raw) == [{"name": "C", "role": "supporting"}]

        # 无效
        assert agent._parse_characters("not json") == []

    def test_run_with_llm(self, base_config):
        """LLM成功返回角色JSON"""
        agent = CharacterGenAgent(base_config)
        mock_response = json.dumps([
            {"name": "小美", "role": "protagonist", "appearance": "美丽",
             "voice_id": "warm_female", "personality": "善良", "age_range": "20-25"},
        ])
        with patch(
            "app.services.llm.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"theme": "复仇短剧"})
        assert result.success is True
        assert len(result.data["characters"]) == 1
        assert result.data["characters"][0]["name"] == "小美"
        assert result.data.get("fallback") is None


# ------------------------------------------------------------------
# StoryboardBreakerAgent Tests
# ------------------------------------------------------------------

class TestStoryboardBreakerAgent:
    def test_run_missing_script(self, base_config):
        agent = StoryboardBreakerAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "剧本" in result.error or "script" in result.error

    def test_run_auto_split_fallback(self, base_config):
        """LLM不可用时，自动按段落切分"""
        agent = StoryboardBreakerAgent(base_config)
        script = "小美在雨中独行。她回忆起那段痛苦的过去。终于她做出了决定。"
        result = agent.run({"script": script, "target_duration": 30})
        assert result.success is True
        storyboard = result.data.get("storyboard", [])
        assert len(storyboard) >= 2
        assert result.data.get("fallback") is True
        for scene in storyboard:
            assert scene.get("scene")
            assert scene.get("duration", 0) > 0
            assert scene.get("shot_type")

    def test_verify_min_2_scenes(self, base_config):
        agent = StoryboardBreakerAgent(base_config)

        good = AgentResult(
            success=True,
            data={"storyboard": [
                {"scene": "场景1", "duration": 5},
                {"scene": "场景2", "duration": 5},
            ]},
        )
        assert agent.verify(good) is True

        too_few = AgentResult(
            success=True,
            data={"storyboard": [{"scene": "只有一个", "duration": 5}]},
        )
        assert agent.verify(too_few) is False

        no_duration = AgentResult(
            success=True,
            data={"storyboard": [
                {"scene": "A", "duration": 0},
                {"scene": "B", "duration": 3},
            ]},
        )
        assert agent.verify(no_duration) is False

    def test_auto_split_handles_single_sentence(self, base_config):
        agent = StoryboardBreakerAgent(base_config)
        result = agent.run({"script": "一句话", "target_duration": 10})
        assert result.success is True
        assert len(result.data["storyboard"]) >= 1

    def test_parse_storyboard_json(self, base_config):
        agent = StoryboardBreakerAgent(base_config)
        raw = json.dumps([
            {"scene": "雨中", "shot_type": "wide_shot", "duration": 5,
             "prompt": "rain scene", "character": "小美", "emotion": "sad"},
        ])
        storyboard = agent._parse_storyboard(raw)
        assert len(storyboard) == 1
        assert storyboard[0]["scene"] == "雨中"

    def test_run_with_llm(self, base_config):
        agent = StoryboardBreakerAgent(base_config)
        mock_response = json.dumps([
            {"scene": "雨中独行", "shot_type": "wide_shot", "duration": 5,
             "prompt": "woman walking in rain", "character": "小美", "emotion": "sad"},
            {"scene": "回忆", "shot_type": "close_up", "duration": 8,
             "prompt": "flashback scene", "character": "小美", "emotion": "painful"},
        ])
        with patch(
            "app.services.llm.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"script": "小美在雨中独行。她回忆过去。"})
        assert result.success is True
        assert len(result.data["storyboard"]) == 2


# ------------------------------------------------------------------
# DubbingAgent Tests
# ------------------------------------------------------------------

class TestDubbingAgent:
    def test_run_missing_script(self, base_config):
        agent = DubbingAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "文案" in result.error or "script" in result.error

    def test_init_defaults(self, base_config):
        agent = DubbingAgent(base_config)
        assert agent.gpt_sovits_api == ""
        assert agent.enabled is True

    def test_init_with_api(self, base_config):
        base_config["dubbing"]["gpt_sovits_api"] = "http://localhost:9880"
        agent = DubbingAgent(base_config)
        assert agent.gpt_sovits_api == "http://localhost:9880"

    def test_verify_needs_audio_file(self, base_config):
        agent = DubbingAgent(base_config)

        no_file = AgentResult(
            success=True,
            data={"dubbed_audio": "/nonexistent.mp3", "mode": "edge_tts_fallback"},
        )
        assert agent.verify(no_file) is False

        no_path = AgentResult(
            success=True,
            data={"dubbed_audio": "", "mode": "edge_tts_fallback"},
        )
        assert agent.verify(no_path) is False

    def test_run_edge_tts_fallback(self, base_config):
        """无GPT-SoVITS API时，降级到Edge TTS"""
        agent = DubbingAgent(base_config)

        with patch("edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()
            mock_comm.return_value = mock_instance

            async def mock_save(path):
                # 创建一个小文件模拟音频
                with open(path, "wb") as f:
                    f.write(b"\x00" * 100)

            mock_instance.save = mock_save

            result = agent.run({"script": "测试文案，这是一段解说词", "session_id": "test"})

        assert result.success is True
        assert result.data.get("mode") == "edge_tts_fallback"
        audio_path = result.data.get("dubbed_audio", "")
        assert audio_path.endswith(".mp3")


# ------------------------------------------------------------------
# VisualAssetAgent Tests
# ------------------------------------------------------------------

class TestVisualAssetAgent:
    def test_run_missing_input(self, base_config):
        agent = VisualAssetAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "标题" in result.error or "title" in result.error

    def test_init_defaults(self, base_config):
        agent = VisualAssetAgent(base_config)
        assert agent.minimax_api_key == ""
        assert agent.vidu_api_key == ""

    def test_verify_needs_assets(self, base_config):
        agent = VisualAssetAgent(base_config)

        has_assets = AgentResult(
            success=True,
            data={"visual_assets": [{"style": "thumbnail", "path": "/tmp/test.png"}]},
        )
        assert agent.verify(has_assets) is True

        no_assets = AgentResult(
            success=True,
            data={"visual_assets": []},
        )
        assert agent.verify(no_assets) is False

    def test_run_pillow_fallback(self, base_config):
        """无MiniMax API时，使用Pillow生成卡片"""
        agent = VisualAssetAgent(base_config)
        result = agent.run({
            "title": "复仇女主逆袭",
            "session_id": "test_visual",
            "styles": ["thumbnail"],
        })
        assert result.success is True
        assets = result.data.get("visual_assets", [])
        assert len(assets) >= 1
        assert assets[0]["style"] == "thumbnail"
        assert os.path.exists(assets[0]["path"])
        assert assets[0]["path"].endswith(".png")

    def test_run_multiple_styles(self, base_config):
        """生成多种风格的卡片"""
        agent = VisualAssetAgent(base_config)
        result = agent.run({
            "title": "测试标题",
            "session_id": "test_multi",
            "styles": ["thumbnail", "tiktok_cover"],
        })
        assert result.success is True
        assets = result.data.get("visual_assets", [])
        assert len(assets) == 2
        styles = {a["style"] for a in assets}
        assert "thumbnail" in styles
        assert "tiktok_cover" in styles

    def test_run_xhs_card(self, base_config):
        """小红书卡片尺寸测试"""
        agent = VisualAssetAgent(base_config)
        result = agent.run({
            "title": "小红书爆款",
            "session_id": "test_xhs",
            "styles": ["xhs_card"],
        })
        assert result.success is True
        assets = result.data.get("visual_assets", [])
        assert len(assets) == 1
        # 检查图片尺寸
        from PIL import Image
        img = Image.open(assets[0]["path"])
        assert img.size == (1080, 1440)  # 3:4 比例


# ------------------------------------------------------------------
# Orchestrator v5.0 Tests
# ------------------------------------------------------------------

class TestOrchestratorV5:
    def test_init_creates_all_18_agents(self, base_config):
        """确认18个Agent全部初始化"""
        orch = AgentOrchestrator(base_config)
        # v3 原有
        assert orch.material_scout is not None
        assert orch.plot_analyzer is not None
        assert orch.script_writer is not None
        assert orch.voice_agent is not None
        assert orch.video_editor is not None
        assert orch.video_gen is not None
        assert orch.broll_matcher is not None
        assert orch.seo_agent is not None
        assert orch.publish_agent is not None
        # v4 新增
        assert orch.persona_master is not None
        assert orch.competitor_decode is not None
        assert orch.topic_engine is not None
        assert orch.review_diagnosis is not None
        assert orch.daily_operator is not None
        # v5 新增
        assert orch.character_gen is not None
        assert orch.storyboard_breaker is not None
        assert orch.dubbing_agent is not None
        assert orch.visual_asset is not None

    def test_run_drama_returns_list(self, base_config):
        """run_drama 返回列表结果"""
        orch = AgentOrchestrator(base_config)
        # ScriptWriter会因为LLM不可用而失败
        results = orch.run_drama(theme="测试短剧", episodes=1)
        assert isinstance(results, list)
        assert len(results) == 1
        # 即使失败也有结构
        assert "session_id" in results[0]
        assert "mode" in results[0]
        assert results[0]["mode"] == "drama"

    def test_run_drama_multiple_episodes(self, base_config):
        """多集测试"""
        orch = AgentOrchestrator(base_config)
        results = orch.run_drama(theme="测试", episodes=3)
        assert len(results) == 3

    def test_run_v4_still_works(self, base_config):
        """v4功能不受影响"""
        orch = AgentOrchestrator(base_config)
        # run() 仍然可用
        results = orch.run(keywords="", urls=[])
        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["stage"] == "material_scout"

    def test_run_daily_still_works(self, base_config):
        """操盘手模式仍然正常"""
        orch = AgentOrchestrator(base_config)
        result = orch.run_daily(batch_size=1, topic_mode="hot")
        assert "success" in result
        assert "persona" in result
        assert "topics" in result

    def test_progress_callback_v5(self, base_config):
        """进度回调包含v5新Agent"""
        orch = AgentOrchestrator(base_config)
        agents_seen = set()

        def cb(agent: str, pct: int, msg: str):
            agents_seen.add(agent)

        orch.set_progress_callback(cb)
        orch.run_drama(theme="测试", episodes=1)

        # 至少能看到这些Agent的进度
        assert "PersonaMaster" in agents_seen
        assert "ScriptWriter" in agents_seen

    def test_save_memory(self, base_config):
        """跨会话记忆持久化测试"""
        orch = AgentOrchestrator(base_config)
        orch._save_memory({"mode": "test", "theme": "测试"})

        memory_path = os.path.join(base_config["app"]["root_dir"], "config", "memory.json")
        assert os.path.exists(memory_path)

        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "sessions" in data
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["mode"] == "test"

    def test_save_memory_append(self, base_config):
        """记忆追加而非覆盖"""
        orch = AgentOrchestrator(base_config)
        orch._save_memory({"mode": "first"})
        orch._save_memory({"mode": "second"})

        memory_path = os.path.join(base_config["app"]["root_dir"], "config", "memory.json")
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["sessions"]) == 2

    def test_save_memory_max_100(self, base_config):
        """记忆最多保留100条"""
        orch = AgentOrchestrator(base_config)
        for i in range(110):
            orch._save_memory({"idx": i})

        memory_path = os.path.join(base_config["app"]["root_dir"], "config", "memory.json")
        with open(memory_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["sessions"]) == 100
        # 最早的被淘汰，保留的是10-109
        assert data["sessions"][0]["idx"] == 10


# ------------------------------------------------------------------
# v5.0 Prompt & Config Assets Tests
# ------------------------------------------------------------------

class TestV5PromptFiles:
    def test_v5_daily_operator_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "app", "prompts", "v5_daily_operator.txt",
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "v5.0" in content or "5.0" in content
        assert "双模式" in content or "drama" in content


class TestV5ConfigAssets:
    def test_memory_json_exists_and_valid(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "config", "memory.json",
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "sessions" in data

    def test_config_toml_v5_sections(self):
        """config.toml包含v5.0新增配置段"""
        import tomli
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "config.toml",
        )
        with open(path, "rb") as f:
            config = tomli.load(f)
        assert "dubbing" in config
        assert "visual_asset" in config
        assert config["app"]["version"] == "5.0.0"
