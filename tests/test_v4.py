"""
v4.0 Agent系统测试
测试新增的5个Agent (PersonaMaster, CompetitorDecode, TopicEngine,
ReviewDiagnosis, DailyOperator) + 升级后的14-Agent Orchestrator
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import AgentResult
from app.agents.persona_master import PersonaMasterAgent
from app.agents.competitor_decode import CompetitorDecodeAgent
from app.agents.topic_engine import TopicEngineAgent
from app.agents.review_diagnosis import ReviewDiagnosisAgent
from app.agents.daily_operator import DailyOperatorAgent
from app.agents.orchestrator import AgentOrchestrator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def base_config():
    """基本配置（v4.0）"""
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
        "app": {
            "root_dir": tmpdir,
        },
    }


@pytest.fixture
def sample_persona():
    """样例创作者画像"""
    return {
        "nickname": "TestCreator",
        "niche": "短剧解说",
        "sub_niches": ["Reddit故事", "社会奇闻"],
        "target_audience": "18-35岁",
        "tone": "犀利吐槽",
        "monetization": ["流量分成"],
        "forbidden_topics": ["政治敏感"],
        "content_frequency": "日更3条",
        "platforms": ["tiktok"],
        "signature_hooks": ["反常识钩子"],
        "brand_keywords": ["爆款"],
    }


@pytest.fixture
def sample_decode_result():
    """样例竞品拆解结果"""
    return {
        "structure": {
            "hook": "你绝对猜不到接下来发生了什么",
            "setup": "一个普通的午后",
            "core": "她当众揭露了真相",
            "closure": "所有人都沉默了",
        },
        "emotion_curve": [
            {"timestamp": "0-3s", "emotion": "好奇", "intensity": 8},
        ],
        "golden_lines": ["这个世界最可怕的不是鬼，是人心"],
        "hook_formula": {
            "name": "反转揭露",
            "template": "你绝对猜不到...",
            "example": "你绝对猜不到这个清洁工其实是亿万富翁",
        },
        "transferable_angles": ["可以用于职场逆袭题材"],
        "viral_score": 8,
    }


@pytest.fixture
def sample_review_result():
    """样例评分结果"""
    return {
        "scores": {
            "hook_power": {"score": 8, "reason": "开头有冲击力", "suggestion": "可以更具体"},
            "emotion_arc": {"score": 7, "reason": "情绪起伏好", "suggestion": "中间段可加强"},
            "pacing": {"score": 8, "reason": "节奏合理", "suggestion": "无"},
            "algorithm_fit": {"score": 7, "reason": "关键词密度好", "suggestion": "增加热门标签"},
            "conversion_clarity": {"score": 6, "reason": "缺少明确CTA", "suggestion": "加评论引导"},
        },
        "overall_score": 7.2,
        "viral_probability": "72%",
        "top_issues": ["转化路径不够清晰"],
        "rewrite_suggestions": ["结尾加一句评论引导"],
        "comment_bait": "你觉得她做对了吗？评论区告诉我",
    }


# ------------------------------------------------------------------
# PersonaMasterAgent Tests
# ------------------------------------------------------------------

class TestPersonaMasterAgent:
    def test_default_persona_when_no_file(self, base_config):
        agent = PersonaMasterAgent(base_config)
        result = agent.run({})
        assert result.success is True
        assert result.data["source"] == "default"
        assert result.data["persona"]["niche"] == "短剧解说"

    def test_save_and_load_persona(self, base_config, sample_persona):
        agent = PersonaMasterAgent(base_config)

        # Save
        agent._save_persona(sample_persona)
        assert os.path.exists(agent.persona_file)

        # Load
        result = agent.run({})
        assert result.success is True
        assert result.data["source"] == "cached"
        assert result.data["persona"]["nickname"] == "TestCreator"

    def test_force_refresh(self, base_config, sample_persona):
        agent = PersonaMasterAgent(base_config)
        agent._save_persona(sample_persona)

        # Force refresh should regenerate (with fallback to default since no LLM)
        result = agent.run({"force_refresh": True})
        assert result.success is True
        # Without LLM, falls back to default
        assert result.data["source"] == "default"

    def test_verify_requires_niche_and_tone(self, base_config):
        agent = PersonaMasterAgent(base_config)

        good = AgentResult(success=True, data={
            "persona": {"niche": "短剧解说", "tone": "犀利"}
        })
        assert agent.verify(good) is True

        no_niche = AgentResult(success=True, data={
            "persona": {"niche": "", "tone": "犀利"}
        })
        assert agent.verify(no_niche) is False

        no_tone = AgentResult(success=True, data={
            "persona": {"niche": "短剧解说", "tone": ""}
        })
        assert agent.verify(no_tone) is False

    def test_generate_persona_with_llm(self, base_config, sample_persona):
        agent = PersonaMasterAgent(base_config)
        mock_response = json.dumps(sample_persona)

        with patch(
            "app.agents.persona_master.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"user_input": "我是短剧解说博主", "force_refresh": True})
            assert result.success is True
            assert result.data["source"] == "generated"
            assert result.data["persona"]["nickname"] == "TestCreator"

    def test_parse_json_from_code_block(self, base_config):
        agent = PersonaMasterAgent(base_config)
        raw = '```json\n{"niche": "test"}\n```'
        assert agent._parse_json(raw) == {"niche": "test"}

    def test_parse_json_embedded(self, base_config):
        agent = PersonaMasterAgent(base_config)
        raw = 'Here is result {"niche": "test"} done'
        assert agent._parse_json(raw) == {"niche": "test"}

    def test_parse_json_invalid(self, base_config):
        agent = PersonaMasterAgent(base_config)
        assert agent._parse_json("not json") == {}


# ------------------------------------------------------------------
# CompetitorDecodeAgent Tests
# ------------------------------------------------------------------

class TestCompetitorDecodeAgent:
    def test_run_missing_text(self, base_config):
        agent = CompetitorDecodeAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "缺少竞品文案" in result.error

    def test_run_with_llm(self, base_config, sample_decode_result):
        agent = CompetitorDecodeAgent(base_config)
        mock_response = json.dumps(sample_decode_result)

        with patch(
            "app.agents.competitor_decode.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({
                "competitor_text": "一段竞品文案...",
                "source": "youtube",
            })
            assert result.success is True
            decode = result.data["decode"]
            assert decode["structure"]["hook"]
            assert decode["hook_formula"]["name"] == "反转揭露"

    def test_verify_requires_structure_and_formula(self, base_config):
        agent = CompetitorDecodeAgent(base_config)

        good = AgentResult(success=True, data={
            "decode": {
                "structure": {"hook": "test"},
                "hook_formula": {"name": "test"},
            }
        })
        assert agent.verify(good) is True

        no_structure = AgentResult(success=True, data={
            "decode": {"hook_formula": {"name": "test"}}
        })
        assert agent.verify(no_structure) is False

        no_formula = AgentResult(success=True, data={
            "decode": {"structure": {"hook": "test"}}
        })
        assert agent.verify(no_formula) is False

    def test_update_formula_library(self, base_config):
        agent = CompetitorDecodeAgent(base_config)
        decode = {
            "hook_formula": {
                "name": "TestFormula",
                "template": "test...",
                "example": "example",
            },
        }

        agent._update_formula_library(decode)

        # Verify file was created
        assert os.path.exists(agent.formula_file)
        with open(agent.formula_file, "r", encoding="utf-8") as f:
            library = json.load(f)
        assert len(library["formulas"]) == 1
        assert library["formulas"][0]["name"] == "TestFormula"

        # Adding same formula again should not duplicate
        agent._update_formula_library(decode)
        with open(agent.formula_file, "r", encoding="utf-8") as f:
            library = json.load(f)
        assert len(library["formulas"]) == 1

    def test_update_hooks_library(self, base_config):
        agent = CompetitorDecodeAgent(base_config)
        decode = {
            "structure": {"hook": "测试钩子"},
            "golden_lines": ["金句1", "金句2"],
        }

        agent._update_hooks_library(decode)

        assert os.path.exists(agent.hooks_file)
        with open(agent.hooks_file, "r", encoding="utf-8") as f:
            library = json.load(f)
        assert "测试钩子" in library["hooks"]
        assert "金句1" in library["golden_lines"]

    def test_load_json_file_default(self, base_config):
        result = CompetitorDecodeAgent._load_json_file(
            "/nonexistent.json", {"key": "default"}
        )
        assert result == {"key": "default"}


# ------------------------------------------------------------------
# TopicEngineAgent Tests
# ------------------------------------------------------------------

class TestTopicEngineAgent:
    def test_run_with_llm(self, base_config):
        agent = TopicEngineAgent(base_config)
        mock_response = json.dumps({
            "topics": [
                {"title": f"选题{i}", "angle": "角度", "hook": f"钩子{i}",
                 "target_emotion": "好奇", "estimated_viral_score": 8,
                 "reference": "ref", "tags": ["tag"]}
                for i in range(7)
            ],
            "strategy_note": "策略说明",
        })

        with patch(
            "app.agents.topic_engine.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"mode": "hot"})
            assert result.success is True
            assert len(result.data["topics"]) == 7
            assert result.data["mode"] == "hot"

    def test_run_invalid_mode_defaults_to_hot(self, base_config):
        agent = TopicEngineAgent(base_config)
        mock_response = json.dumps({
            "topics": [
                {"title": f"t{i}", "hook": f"h{i}", "angle": "a", "target_emotion": "e",
                 "estimated_viral_score": 7, "reference": "", "tags": []}
                for i in range(5)
            ],
            "strategy_note": "",
        })

        with patch(
            "app.agents.topic_engine.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"mode": "invalid_mode"})
            assert result.success is True
            assert result.data["mode"] == "hot"

    def test_verify_min_3_topics(self, base_config):
        agent = TopicEngineAgent(base_config)

        too_few = AgentResult(success=True, data={
            "topics": [{"title": "t", "hook": "h"}]
        })
        assert agent.verify(too_few) is False

        enough = AgentResult(success=True, data={
            "topics": [
                {"title": f"t{i}", "hook": f"h{i}"} for i in range(3)
            ]
        })
        assert agent.verify(enough) is True

    def test_verify_requires_title_and_hook(self, base_config):
        agent = TopicEngineAgent(base_config)

        missing_hook = AgentResult(success=True, data={
            "topics": [
                {"title": "t1", "hook": ""},
                {"title": "t2", "hook": "h2"},
                {"title": "t3", "hook": "h3"},
            ]
        })
        assert agent.verify(missing_hook) is False


# ------------------------------------------------------------------
# ReviewDiagnosisAgent Tests
# ------------------------------------------------------------------

class TestReviewDiagnosisAgent:
    def test_run_missing_script(self, base_config):
        agent = ReviewDiagnosisAgent(base_config)
        result = agent.run({})
        assert result.success is False
        assert "缺少待诊断文案" in result.error

    def test_run_with_llm(self, base_config, sample_review_result):
        agent = ReviewDiagnosisAgent(base_config)
        mock_response = json.dumps(sample_review_result)

        with patch(
            "app.agents.review_diagnosis.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"script": "一段测试文案" * 20, "title": "测试"})
            assert result.success is True
            review = result.data["review"]
            assert review["overall_score"] == 7.2
            assert review["viral_probability"] == "72%"
            assert len(review["scores"]) == 5

    def test_verify_needs_scores_and_overall(self, base_config):
        agent = ReviewDiagnosisAgent(base_config)

        good = AgentResult(success=True, data={
            "review": {
                "scores": {
                    "hook_power": {"score": 8},
                    "emotion_arc": {"score": 7},
                    "pacing": {"score": 8},
                },
                "overall_score": 7.7,
            }
        })
        assert agent.verify(good) is True

        no_scores = AgentResult(success=True, data={
            "review": {"scores": {}, "overall_score": 7}
        })
        assert agent.verify(no_scores) is False

        no_overall = AgentResult(success=True, data={
            "review": {
                "scores": {"a": {"score": 1}, "b": {"score": 2}, "c": {"score": 3}},
            }
        })
        assert agent.verify(no_overall) is False

    def test_auto_calculate_overall(self, base_config):
        agent = ReviewDiagnosisAgent(base_config)
        # Response without overall_score
        mock_response = json.dumps({
            "scores": {
                "hook_power": {"score": 8, "reason": "r", "suggestion": "s"},
                "emotion_arc": {"score": 6, "reason": "r", "suggestion": "s"},
            },
            "top_issues": [],
            "rewrite_suggestions": [],
        })

        with patch(
            "app.agents.review_diagnosis.generate_response_from_config",
            return_value=mock_response,
        ):
            result = agent.run({"script": "测试文案" * 20})
            assert result.success is True
            # Should auto-calculate: (8+6)/2 = 7.0
            assert result.data["review"]["overall_score"] == 7.0


# ------------------------------------------------------------------
# DailyOperatorAgent Tests
# ------------------------------------------------------------------

class TestDailyOperatorAgent:
    def test_run_with_default_topics(self, base_config):
        agent = DailyOperatorAgent(base_config)
        result = agent.run({"batch_size": 3})
        assert result.success is True
        plan = result.data["daily_plan"]
        assert len(plan["topics"]) == 3
        assert len(plan["calendar_entries"]) == 3
        assert plan["status"] == "ready"

    def test_run_with_pre_provided_topics(self, base_config):
        agent = DailyOperatorAgent(base_config)
        topics = [
            {"title": "选题A"},
            {"title": "选题B"},
        ]
        result = agent.run({"batch_size": 2, "topics": topics})
        assert result.success is True
        assert len(result.data["daily_plan"]["topics"]) == 2
        assert result.data["daily_plan"]["topics"][0]["title"] == "选题A"

    def test_calendar_generation(self, base_config):
        agent = DailyOperatorAgent(base_config)
        result = agent.run({"batch_size": 5})
        assert result.success is True
        entries = result.data["daily_plan"]["calendar_entries"]
        assert len(entries) == 5
        # First 3 should be same day, different times
        times = [e["time"] for e in entries[:3]]
        assert "09:00" in times
        assert "14:00" in times
        assert "20:00" in times

    def test_verify_needs_topics_and_calendar(self, base_config):
        agent = DailyOperatorAgent(base_config)

        good = AgentResult(success=True, data={
            "daily_plan": {
                "topics": [{"title": "t"}],
                "calendar_entries": [{"date": "2026-01-01"}],
            }
        })
        assert agent.verify(good) is True

        no_topics = AgentResult(success=True, data={
            "daily_plan": {
                "topics": [],
                "calendar_entries": [{"date": "2026-01-01"}],
            }
        })
        assert agent.verify(no_topics) is False

        no_calendar = AgentResult(success=True, data={
            "daily_plan": {
                "topics": [{"title": "t"}],
                "calendar_entries": [],
            }
        })
        assert agent.verify(no_calendar) is False

    def test_plan_saved_to_file(self, base_config):
        agent = DailyOperatorAgent(base_config)
        result = agent.run({"batch_size": 2})
        plan_path = result.data.get("plan_path", "")
        assert plan_path
        assert os.path.exists(plan_path)

        with open(plan_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["batch_size"] == 2

    def test_next_steps_auto_mode(self, base_config):
        agent = DailyOperatorAgent(base_config)
        result = agent.run({"batch_size": 2, "auto_mode": True})
        steps = result.data.get("next_steps", [])
        assert len(steps) > 0
        # Auto mode should not have pause step
        assert not any("⏸️" in s for s in steps)

    def test_next_steps_manual_mode(self, base_config):
        agent = DailyOperatorAgent(base_config)
        result = agent.run({"batch_size": 2, "auto_mode": False})
        steps = result.data.get("next_steps", [])
        assert any("⏸️" in s for s in steps)


# ------------------------------------------------------------------
# Orchestrator v4.0 Tests
# ------------------------------------------------------------------

class TestOrchestratorV4:
    def test_init_creates_all_14_agents(self, base_config):
        orch = AgentOrchestrator(base_config)
        # v3.0 agents
        assert orch.material_scout is not None
        assert orch.plot_analyzer is not None
        assert orch.script_writer is not None
        assert orch.voice_agent is not None
        assert orch.video_editor is not None
        assert orch.video_gen is not None
        assert orch.broll_matcher is not None
        assert orch.seo_agent is not None
        assert orch.publish_agent is not None
        # v4.0 new agents
        assert orch.persona_master is not None
        assert orch.competitor_decode is not None
        assert orch.topic_engine is not None
        assert orch.review_diagnosis is not None
        assert orch.daily_operator is not None

    def test_run_daily_basic(self, base_config):
        """run_daily should return a plan even without LLM"""
        orch = AgentOrchestrator(base_config)
        result = orch.run_daily(batch_size=3, topic_mode="hot")
        # PersonaMaster and TopicEngine may fail without LLM,
        # but DailyOperator should still produce a plan
        assert "daily_plan" in result

    def test_run_decode_missing_text(self, base_config):
        orch = AgentOrchestrator(base_config)
        result = orch.run_decode("")
        assert result["success"] is False

    def test_run_decode_with_llm(self, base_config, sample_decode_result):
        orch = AgentOrchestrator(base_config)
        mock_response = json.dumps(sample_decode_result)

        with patch(
            "app.agents.competitor_decode.generate_response_from_config",
            return_value=mock_response,
        ):
            result = orch.run_decode("测试竞品文案", source="reddit")
            assert result["success"] is True
            assert result["decode"]["structure"]["hook"]

    def test_run_topics_basic(self, base_config):
        orch = AgentOrchestrator(base_config)
        mock_topics = json.dumps({
            "topics": [
                {"title": f"t{i}", "hook": f"h{i}", "angle": "a",
                 "target_emotion": "好奇", "estimated_viral_score": 8,
                 "reference": "", "tags": []}
                for i in range(5)
            ],
            "strategy_note": "test",
        })

        with patch(
            "app.agents.topic_engine.generate_response_from_config",
            return_value=mock_topics,
        ):
            result = orch.run_topics(mode="hot")
            assert result["success"] is True
            assert len(result["topics"]) == 5

    def test_run_review_basic(self, base_config, sample_review_result):
        orch = AgentOrchestrator(base_config)
        mock_response = json.dumps(sample_review_result)

        with patch(
            "app.agents.review_diagnosis.generate_response_from_config",
            return_value=mock_response,
        ):
            result = orch.run_review("测试文案" * 20, title="测试标题")
            assert result["success"] is True
            assert result["review"]["overall_score"] == 7.2

    def test_run_v3_still_works(self, base_config):
        """v3.0 run() method should still work"""
        orch = AgentOrchestrator(base_config)
        results = orch.run(keywords="", urls=[])
        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["stage"] == "material_scout"

    def test_progress_callback_v4(self, base_config):
        """Progress callback should work with v4 methods"""
        orch = AgentOrchestrator(base_config)
        calls = []
        orch.set_progress_callback(lambda a, p, m: calls.append((a, p, m)))
        orch.run_decode("")
        assert len(calls) > 0
        assert calls[0][0] == "CompetitorDecode"


# ------------------------------------------------------------------
# v4.0 Prompt files existence tests
# ------------------------------------------------------------------

class TestV4PromptFiles:
    def test_competitor_decode_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "v4_competitor_decode_prompt.txt",
        )
        assert os.path.exists(path)

    def test_review_diagnosis_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "v4_review_diagnosis_prompt.txt",
        )
        assert os.path.exists(path)

    def test_topic_engine_prompt_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "prompts", "v4_topic_engine_prompt.txt",
        )
        assert os.path.exists(path)


# ------------------------------------------------------------------
# v4.0 Config asset files existence tests
# ------------------------------------------------------------------

class TestV4ConfigAssets:
    def test_formula_library_exists_and_valid(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "formula-library.json",
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "formulas" in data
        assert len(data["formulas"]) > 0
        assert data["formulas"][0]["name"]
        assert data["formulas"][0]["template"]

    def test_hooks_library_exists_and_valid(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "hooks-library.json",
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "hooks" in data
        assert "golden_lines" in data
        assert len(data["hooks"]) > 0
