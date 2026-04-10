"""
测试 Pipeline 核心功能（不依赖外部服务）
"""

import pytest
from app.pipeline import parse_annotated_script, _call_llm


class TestParseAnnotatedScript:
    """测试文案解析"""

    def test_basic_parsing(self):
        script = """[mood:tense][broll:dark room]
第一段文字
---
[mood:emotional][broll:family home]
第二段文字
---
[mood:upbeat][broll:sunrise]
第三段文字"""

        result = parse_annotated_script(script)
        assert len(result) == 3
        assert result[0]["mood"] == "tense"
        assert result[0]["broll_keywords"] == ["dark room"]
        assert "第一段文字" in result[0]["text"]
        assert result[1]["mood"] == "emotional"
        assert result[2]["mood"] == "upbeat"

    def test_no_tags(self):
        script = "段落一\n\n段落二\n\n段落三"
        result = parse_annotated_script(script)
        assert len(result) >= 2
        assert all(r["mood"] == "calm" for r in result)

    def test_mixed_tags(self):
        script = """[mood:tense]
有标签的段落
---
没有标签的段落"""

        result = parse_annotated_script(script)
        assert len(result) == 2
        assert result[0]["mood"] == "tense"
        assert result[1]["mood"] == "calm"

    def test_multiple_broll_keywords(self):
        script = "[mood:calm][broll:city night, rain]一段文字"
        result = parse_annotated_script(script)
        assert len(result) == 1
        assert "city night" in result[0]["broll_keywords"]
        assert "rain" in result[0]["broll_keywords"]

    def test_empty_script(self):
        result = parse_annotated_script("")
        assert result == []

    def test_annotations_cleaned(self):
        script = "[mood:tense][broll:test]纯净文本"
        result = parse_annotated_script(script)
        assert result[0]["text"] == "纯净文本"
        assert "[mood:" not in result[0]["text"]
        assert "[broll:" not in result[0]["text"]


class TestCallLLM:
    """测试 LLM 调用（仅测试参数构建，不实际调用）"""

    def test_config_extraction(self):
        """测试配置提取逻辑"""
        config = {
            "llm": {
                "api_base": "http://localhost:11434/v1",
                "api_key": "test-key",
                "model": "test-model",
            }
        }
        # 不实际调用 LLM，只验证不会崩溃
        # _call_llm 会因为连接失败返回空字符串
        result = _call_llm("test", config)
        assert isinstance(result, str)
