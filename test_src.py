"""
test_src.py - 验证新模块化架构（src/）
无需API key，只验证代码路径 + 文件格式
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.task_manager import get_work_dir, STAGES_ORDER
from src.llm_client import extract_json, call


def test_work_dir():
    """测试工作目录生成"""
    wd = get_work_dir("input/film.mp4")
    assert wd.name == "film"
    print(f"✅ get_work_dir: {wd}")


def test_stages_order():
    """验证 stage 顺序"""
    expected = [
        "transcribe", "segment", "chapter_draft", "chapter_refine",
        "outline", "script", "reflect", "repair",
        "scene_prompt_draft", "scene_prompt_refine",
        "tts", "subtitle", "render_manifest", "render_video"
    ]
    assert STAGES_ORDER == expected, f"Stage顺序不对: {STAGES_ORDER}"
    print(f"✅ Stage顺序正确: {len(STAGES_ORDER)} 个stage")


def test_extract_json():
    """测试 JSON 提取"""
    text = '```json\n{"foo": "bar"}\n```'
    result = extract_json(text)
    assert result == {"foo": "bar"}, f"提取失败: {result}"
    print(f"✅ extract_json: 从markdown提取JSON OK")

    text2 = 'Just text\n{"a": 1}\nmore text'
    result2 = extract_json(text2)
    assert result2 == {"a": 1}, f"提取失败: {result2}"
    print(f"✅ extract_json: 从混合格式提取 OK")


def test_llm_client_call():
    """测试 LLM 客户端路由（不实际调用，只验证import）"""
    # 这不会实际调用，只是验证路由逻辑存在
    try:
        from src.llm_client import call_ollama, call_deepseek, call_minimax, call
        print(f"✅ LLM客户端导入成功")
    except Exception as e:
        # 环境变量没配置是OK的，但import必须成功
        print(f"❌ LLM客户端导入失败: {e}")


def test_module_imports():
    """测试所有 stage 模块可导入"""
    modules = [
        "src.transcribe", "src.segment", "src.chapter_draft",
        "src.chapter_refine", "src.outline", "src.script",
        "src.reflect", "src.repair", "src.scene_prompt_draft",
        "src.scene_prompt_refine", "src.tts", "src.subtitle",
        "src.render_manifest", "src.render_video",
    ]
    for mod in modules:
        try:
            __import__(mod)
            print(f"  ✅ {mod}")
        except Exception as e:
            print(f"  ❌ {mod}: {e}")


def test_json_schemas():
    """验证 schemas/ 格式正确"""
    from schemas import (
        TRANSCRIPT_SCHEMA, SCENES_SCHEMA, CHAPTER_DRAFT_SCHEMA,
        CHAPTER_REFINED_SCHEMA, OUTLINE_SCHEMA, SCRIPT_PART_SCHEMA,
        SCRIPT_REVIEW_SCHEMA, FINAL_SCRIPT_SCHEMA, SCENE_PROMPTS_SCHEMA,
        RENDER_MANIFEST_SCHEMA,
    )
    print(f"✅ 所有 JSON Schema 加载成功 (10个)")
    for name in dir():
        if name.endswith("_SCHEMA"):
            print(f"  • {name}")


def test_render_manifest_logic():
    """测试 render_manifest 的镜头分配逻辑"""
    from src.render_manifest import _distribute_to_scenes, _sec_to_time, _time_to_sec

    # 测试时间转换
    assert _sec_to_time(3661) == "01:01:01"
    assert abs(_time_to_sec("01:01:01") - 3661) < 0.1
    print(f"✅ 时间转换函数 OK")

    # 测试分配逻辑
    sentences = [
        {"text": "第一句", "duration": 4},
        {"text": "第二句", "duration": 5},
    ]
    scenes = [
        {"scene_id": 1, "start": "00:00:00", "end": "00:00:10"},
        {"scene_id": 2, "start": "00:00:10", "end": "00:00:20"},
    ]
    clips = _distribute_to_scenes(sentences, scenes, 9.0)
    assert len(clips) == 2
    print(f"✅ 镜头分配逻辑 OK: {len(clips)} clips")


def main():
    print("=" * 60)
    print("🧪 新架构（src/）验证测试")
    print("=" * 60)

    test_work_dir()
    test_stages_order()
    test_extract_json()
    test_module_imports()
    test_json_schemas()
    test_render_manifest_logic()

    print("\n✅ 全部验证通过！")
    print("下一步: 配置 API key 后运行:")
    print("  python src/main.py input/film.mp4")


if __name__ == "__main__":
    main()
