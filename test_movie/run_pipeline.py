"""
电影流水线测试脚本
==================
用法:
  python test_movie/run_pipeline.py

本脚本:
1. 使用本地测试视频
2. 执行 Stage 1-2（转写+镜头检测，不需API）
3. Stage 3-9 使用 mock 数据演示完整流程
4. 输出 render_manifest.json 到 test_movie/output/
"""

import json
import os
import sys
import shutil
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.movie.pipeline import (
    MovieNarrationPipeline,
    PipelineConfig,
    STYLE_PRESETS,
)
from app.services.movie.knowledge_base import KnowledgeBase


# ── 测试配置 ────────────────────────────────────────────────────────────────
VIDEO_PATH = Path(__file__).parent / "test_movie.mp4"
WORK_DIR = Path(__file__).parent / "output"
WORK_DIR.mkdir(exist_ok=True)

# 检查测试视频
if not VIDEO_PATH.exists():
    print(f"❌ 测试视频不存在: {VIDEO_PATH}")
    print("  运行: python test_movie/make_test_video.py")
    sys.exit(1)

print(f"✅ 测试视频: {VIDEO_PATH} ({os.path.getsize(VIDEO_PATH)} bytes)")


# ── Mock MiniMax 2.7 ─────────────────────────────────────────────────────────
# 用于没有API key时演示完整流程

STYLE_MOCK_RESPONSES = {
    "悬疑反转": {
        "chapters": {
            "chapters": [
                {
                    "id": 1, "title": "神秘的开端", "start_sec": 0, "end_sec": 60,
                    "summary": "主角在一个陌生的房间醒来，无法回忆过去",
                    "key_events": ["主角醒来", "陌生房间", "失忆"],
                    "characters": ["主角（男/女）"]
                },
                {
                    "id": 2, "title": "层层迷雾", "start_sec": 60, "end_sec": 120,
                    "summary": "主角发现周围所有人都在监视他",
                    "key_events": ["发现监视", "逃离尝试", "真相浮现"],
                    "characters": ["主角", "神秘人"]
                },
                {
                    "id": 3, "title": "最终真相", "start_sec": 120, "end_sec": 180,
                    "summary": "所有谜题在结局一次性揭开",
                    "key_events": ["真相揭露", "终极反转", "震撼结局"],
                    "characters": ["主角", "幕后黑手"]
                },
            ],
            "total_duration_sec": 180,
            "genre": "悬疑",
            "estimated_theme": "记忆与身份"
        },
        "outline": {
            "part1": {
                "theme": "神秘开局", "time_range": "0-60秒",
                "hook": "他醒来时躺在一个纯白的房间里，墙上有个洞，他完全不记得自己是谁。",
                "key_points": ["陌生房间醒来", "完全失忆", "墙上的洞"],
                "ending_hook": "但当他仔细看那个洞时，发现洞的边缘有血迹..."
            },
            "part2": {
                "theme": "迷雾重重", "time_range": "60-120秒",
                "hook": "他开始尝试逃出去，却发现每个出口都通向同一个房间。",
                "key_points": ["循环房间", "发现监视者", "记忆碎片出现"],
                "ending_hook": "那个一直在监视他的人，竟然和他长得一模一样..."
            },
            "part3": {
                "theme": "终极真相", "time_range": "120-180秒",
                "hook": "当真相揭晓的那一刻，他才知道，原来他不是被困在这里——这里是他的杰作。",
                "key_points": ["真相揭露", "身份逆转", "震撼结局"],
                "ending_hook": "他微笑着按下开关，房间开始崩塌。他说：'这是第九次了。'"
            },
            "overall_arc": "一个失忆者被困在循环房间中，最终发现自己是这整个实验的设计者"
        },
        "script_part1": {
            "part_num": 1,
            "paragraph_text": "他醒来的时候，躺在一个纯白色的房间里。四周是光秃秃的墙壁，头顶是刺眼的日光灯。他完全不记得自己是谁，也不记得自己是怎么来到这里的。唯一能确定的，就是墙上那个洞——一个刚好能伸进一只手的洞。他慢慢走近那个洞，发现洞的边缘，有干涸的血迹。",
            "sentences": [
                {"id": 1, "text": "他醒来的时候，躺在一个纯白色的房间里。", "estimated_duration_sec": 4},
                {"id": 2, "text": "四周是光秃秃的墙壁，头顶是刺眼的日光灯。", "estimated_duration_sec": 5},
                {"id": 3, "text": "他完全不记得自己是谁，也不记得自己是怎么来到这里的。", "estimated_duration_sec": 6},
                {"id": 4, "text": "唯一能确定的，就是墙上那个洞——一个刚好能伸进一只手的洞。", "estimated_duration_sec": 6},
                {"id": 5, "text": "他慢慢走近那个洞，发现洞的边缘，有干涸的血迹。", "estimated_duration_sec": 5},
            ],
            "total_estimated_duration_sec": 26,
            "hook_strength": 9,
            "pacing_score": 8,
        },
        "script_part2": {
            "part_num": 2,
            "paragraph_text": "他开始寻找出口，却发现一个诡异的事实——无论他往哪个方向走，最终都会回到这个房间。他被困住了。更可怕的是，他开始感觉到，有一双眼睛一直在某个地方注视着他。那种感觉越来越强烈，直到他在天花板的角落发现了一个微型摄像头。",
            "sentences": [
                {"id": 1, "text": "他开始寻找出口，却发现一个诡异的事实——无论他往哪个方向走，最终都会回到这个房间。", "estimated_duration_sec": 7},
                {"id": 2, "text": "他被困住了。", "estimated_duration_sec": 2},
                {"id": 3, "text": "更可怕的是，他开始感觉到，有一双眼睛一直在某个地方注视着他。", "estimated_duration_sec": 6},
                {"id": 4, "text": "那种感觉越来越强烈，直到他在天花板的角落发现了一个微型摄像头。", "estimated_duration_sec": 6},
                {"id": 5, "text": "就在这时，门外传来了声音。", "estimated_duration_sec": 3},
            ],
            "total_estimated_duration_sec": 24,
            "hook_strength": 8,
            "pacing_score": 9,
        },
        "script_part3": {
            "part_num": 3,
            "paragraph_text": "门开了。走进来的人，让他彻底崩溃——那是一张和他一模一样的脸。那个人说：欢迎回来，这是你的第九次实验。每一次，你都会忘记一切，然后重新开始。他终于明白了，那个洞不是逃脱的出口，而是他亲手埋下的记忆封印。",
            "sentences": [
                {"id": 1, "text": "门开了。走进来的人，让他彻底崩溃——那是一张和他一模一样的脸。", "estimated_duration_sec": 6},
                {"id": 2, "text": "那个人说：欢迎回来，这是你的第九次实验。每一次，你都会忘记一切，然后重新开始。", "estimated_duration_sec": 8},
                {"id": 3, "text": "他终于明白了，那个洞不是逃脱的出口，而是他亲手埋下的记忆封印。", "estimated_duration_sec": 6},
                {"id": 4, "text": "他微笑着按下开关，房间开始崩塌。", "estimated_duration_sec": 4},
                {"id": 5, "text": "这是他给自己留下的，最后一个出口。", "estimated_duration_sec": 4},
            ],
            "total_estimated_duration_sec": 28,
            "hook_strength": 9,
            "pacing_score": 9,
        },
        "reflection": {
            "issues_found": ["第一段开头稍慢", "第三段最后一句略显多余"],
            "issues_fixed": ["将开头改为更直接的方式", "删除最后一句重复含义"],
            "revised_script": {
                "part_num": 3,
                "paragraph_text": "门开了。走进来的人，让他彻底崩溃——那是一张和他一模一样的脸。那个人说：欢迎回来，这是你的第九次实验。每一次，你都会忘记一切，然后重新开始。他终于明白了，那个洞不是逃脱的出口，而是他亲手埋下的记忆封印。他微笑着按下开关，房间开始崩塌。",
                "sentences": [
                    {"id": 1, "text": "门开了。走进来的人，让他彻底崩溃——那是一张和他一模一样的脸。", "estimated_duration_sec": 6},
                    {"id": 2, "text": "那个人说：欢迎回来，这是你的第九次实验。每一次，你都会忘记一切，然后重新开始。", "estimated_duration_sec": 8},
                    {"id": 3, "text": "他终于明白了，那个洞不是逃脱的出口，而是他亲手埋下的记忆封印。", "estimated_duration_sec": 6},
                    {"id": 4, "text": "他微笑着按下开关，房间开始崩塌。", "estimated_duration_sec": 4},
                ],
                "total_estimated_duration_sec": 24,
            },
            "overall_score": 8.5,
        },
        "judge": {
            "scores": [
                {
                    "part": 1, "hook_score": 9, "clarity_score": 8,
                    "pacing_score": 8, "drama_score": 9,
                    "repetition_score": 8, "camera_match_score": 7,
                    "total_score": 8.2,
                    "issues": [],
                    "recommendation": "PASS"
                },
                {
                    "part": 2, "hook_score": 8, "clarity_score": 8,
                    "pacing_score": 9, "drama_score": 8,
                    "repetition_score": 9, "camera_match_score": 7,
                    "total_score": 8.2,
                    "issues": [],
                    "recommendation": "PASS"
                },
                {
                    "part": 3, "hook_score": 9, "clarity_score": 9,
                    "pacing_score": 9, "drama_score": 9,
                    "repetition_score": 8, "camera_match_score": 8,
                    "total_score": 8.8,
                    "issues": [],
                    "recommendation": "PASS"
                },
            ],
        },
        "scene_prompts": {
            "scene_prompts": [
                {
                    "sentence_id": 1,
                    "original_narration": "门开了。走进来的人，让他彻底崩溃——那是一张和他一模一样的脸。",
                    "hyde_prompt": "近景/特写：门缓缓打开，一个穿西装的男人走进白色房间，他的脸部表情从平静逐渐转为震惊。光线从门缝透入，形成强烈的明暗对比。",
                    "keywords": ["门开", "相同的脸", "震惊", "特写", "白色房间"],
                    "camera_type": "近景"
                },
            ],
        },
    },
}


class MockMinimax:
    """Mock MiniMax 2.7 API for testing"""

    def chat_completions_create(self, model, messages, **kwargs):
        user_msg = messages[-1]["content"] if messages else ""

        # 判断是哪个stage（按关键词精确匹配，避免顺序干扰）
        if "part1" in user_msg and ("theme" in user_msg or "hook" in user_msg):
            # Outline stage: has "part1" and theme/hook fields
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["outline"]
        elif "章节摘要" in user_msg or ("chapters" in user_msg and "genre" in user_msg):
            # Chapter stage: has chapters + genre fields
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["chapters"]
        elif "第1段" in user_msg and "详细解说" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["script_part1"]
        elif "第2段" in user_msg and "详细解说" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["script_part2"]
        elif "第3段" in user_msg and "详细解说" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["script_part3"]
        elif "检查" in user_msg and "解说脚本" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["reflection"]
        elif "打分" in user_msg or "质量评估" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["judge"]
        elif "镜头提示" in user_msg or "HyDE" in user_msg:
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["scene_prompts"]
        else:
            # Default outline
            data = STYLE_MOCK_RESPONSES["悬疑反转"]["outline"]

        class Choice:
            class Message:
                content = json.dumps(data, ensure_ascii=False)
            message = Message()
            index = 0

        class MockResponse:
            choices = [Choice()]

        return MockResponse()


def run_with_mock():
    """使用Mock API运行完整流水线（不需真实API key）"""
    print("\n" + "="*60)
    print("🎬 电影自动浓缩解说系统 - Mock模式演示")
    print("="*60)

    # ── Stage 1: 转写 ─────────────────────────────────────────────────────
    print("\n📋 Stage 1: WhisperX 转写...")
    cfg = PipelineConfig(
        work_dir=str(WORK_DIR),
        whisperx_model="base",
        style="悬疑反转",
    )
    pipeline = MovieNarrationPipeline(cfg)

    # Pipeline creates session subdirectory, get it
    session_work_dir = list(WORK_DIR.glob("session_*"))
    actual_work_dir = session_work_dir[0] if session_work_dir else WORK_DIR
    transcript_path = actual_work_dir / "transcript.json"

    if not transcript_path.exists():
        r = pipeline._stage_transcribe(str(VIDEO_PATH))
        if r.success:
            # Check if whisper actually got content
            with open(r.output_path) as f:
                td = json.load(f)
            num_sentences = len(td.get("transcript", []))
            print(f"  ✅ 转写完成: {r.output_path} ({num_sentences} 句)")

            # If 0 sentences (testsrc has no speech), use mock transcript for demo
            if num_sentences == 0:
                print("  ⚠️  testsrc无语音，使用Mock转写数据演示后续流程...")
                mock_transcript = {
                    "transcript": [
                        {"start": 0.0, "end": 5.0, "text": "他醒来的时候，躺在一个纯白色的房间里。"},
                        {"start": 5.0, "end": 10.0, "text": "四周是光秃秃的墙壁，头顶是刺眼的日光灯。"},
                        {"start": 10.0, "end": 15.0, "text": "他完全不记得自己是谁，也不记得是怎么来到这里的。"},
                        {"start": 15.0, "end": 20.0, "text": "唯一能确定的，就是墙上那个洞——刚好能伸进一只手。"},
                    ],
                    "total_duration": 20.0,
                    "language": "zh",
                }
                with open(r.output_path, "w", encoding="utf-8") as f:
                    json.dump(mock_transcript, f, ensure_ascii=False, indent=2)
        else:
            print(f"  ❌ 转写失败: {r.error}")
            return
    else:
        print(f"  ✅ 使用已有: {transcript_path}")

    # ── Stage 2: 镜头检测 ────────────────────────────────────────────────
    print("\n📋 Stage 2: PySceneDetect 镜头检测...")
    scenes_path = actual_work_dir / "scenes.json"
    if not scenes_path.exists():
        r = pipeline._stage_segment(str(VIDEO_PATH))
        if r.success:
            print(f"  ✅ 镜头检测完成: {r.output_path}")
            with open(r.output_path) as f:
                scenes = json.load(f)
            print(f"     共 {len(scenes.get('scenes', []))} 个镜头")
            # If 0 scenes (testsrc uniform pattern), use mock scenes for demo
            if len(scenes.get('scenes', [])) == 0:
                print("  ⚠️  testsrc无明显镜头切换，使用Mock镜头数据...")
                mock_scenes = {
                    "scenes": [
                        {"id": 0, "start_sec": 0.0, "end_sec": 5.0, "duration_sec": 5.0},
                        {"id": 1, "start_sec": 5.0, "end_sec": 10.0, "duration_sec": 5.0},
                        {"id": 2, "start_sec": 10.0, "end_sec": 15.0, "duration_sec": 5.0},
                        {"id": 3, "start_sec": 15.0, "end_sec": 20.0, "duration_sec": 5.0},
                    ]
                }
                with open(r.output_path, "w", encoding="utf-8") as f:
                    json.dump(mock_scenes, f, ensure_ascii=False, indent=2)
        else:
            print(f"  ❌ 镜头检测失败: {r.error}")
            return
    else:
        print(f"  ✅ 使用已有: {scenes_path}")

    # ── 注入 Mock MiniMax ──────────────────────────────────────────────
    print("\n📋 Stage 3-9: MiniMax 2.7 (Mock模式)...")

    # Patch the _call_minimax to use mock
    original_call = pipeline._call_minimax

    def mock_call(prompt, system=""):
        mock = MockMinimax()
        result = mock.chat_completions_create(pipeline.cfg.model, [{"role": "user", "content": prompt}])
        return result.choices[0].message.content

    pipeline._call_minimax = mock_call

    # ── Stage 3: 章节摘要 ──────────────────────────────────────────────
    chapters_path = actual_work_dir / "chapters.json"
    if not chapters_path.exists():
        r = pipeline._stage_chapter(str(transcript_path), str(scenes_path))
        if r.success:
            print(f"  ✅ 章节摘要完成: {r.output_path}")
            data = r.data or {}
            print(f"     共 {len(data.get('chapters', []))} 章")
        else:
            print(f"  ❌ 章节摘要失败: {r.error}")
            return
    else:
        print(f"  ✅ 使用已有: {chapters_path}")

    # ── Stage 4: 三段式大纲 ───────────────────────────────────────────
    outline_path = actual_work_dir / "outline.json"
    if not outline_path.exists():
        r = pipeline._stage_outline(str(chapters_path))
        if r.success:
            print(f"  ✅ 三段式大纲完成: {r.output_path}")
            Path(str(r.output_path) + ".done").touch()
        else:
            print(f"  ❌ 大纲失败: {r.error}")
            return
    else:
        print(f"  ✅ 使用已有: {outline_path}")

    # ── Stage 5: 详细脚本 ─────────────────────────────────────────────
    script_dir = actual_work_dir / "scripts"
    script_dir.mkdir(exist_ok=True)
    for i in range(1, 4):
        sp = script_dir / f"script_part{i}.json"
        if not sp.exists():
            r = pipeline._stage_script(str(outline_path), part_num=i)
            if r.success:
                print(f"  ✅ 第{i}段脚本: {sp.name}")
                Path(str(sp) + ".done").touch()
            else:
                print(f"  ❌ 第{i}段脚本失败: {r.error}")
        else:
            print(f"  ✅ 使用已有: {sp.name}")

    # ── Stage 6: Reflection ────────────────────────────────────────────
    final_dir = actual_work_dir / "final_scripts"
    final_dir.mkdir(exist_ok=True)
    for i in range(1, 4):
        sp = script_dir / f"script_part{i}.json"
        fp = final_dir / f"script_part{i}.json"
        if not fp.exists():
            r = pipeline._stage_reflection(str(sp))
            if r.success:
                print(f"  ✅ 第{i}段Reflection: {fp.name}")
                Path(str(fp) + ".done").touch()
            else:
                print(f"  ⚠️  Reflection失败，使用原脚本: {r.error}")
                shutil.copy2(sp, fp)
        else:
            print(f"  ✅ 使用已有: {fp.name}")

    # ── Stage 7: LLM-as-Judge ─────────────────────────────────────────
    judge_path = actual_work_dir / "judge_scores.json"
    if not judge_path.exists():
        final_paths = [str(final_dir / f"script_part{i}.json") for i in range(1, 4)]
        r = pipeline._stage_judge(final_paths)
        if r.success:
            print(f"  ✅ LLM-as-Judge评分: {r.output_path}")
            Path(str(r.output_path) + ".done").touch()
            # 显示评分
            scores = r.data.get("scores", [])
            for s in scores:
                print(f"     第{s['part']}段: 总分={s['total_score']} 推荐={s['recommendation']}")
        else:
            print(f"  ⚠️  Judge失败: {r.error}")
    else:
        print(f"  ✅ 使用已有: {judge_path}")

    # ── Stage 8: 镜头提示 ─────────────────────────────────────────────
    prompts_dir = actual_work_dir / "scene_prompts"
    prompts_dir.mkdir(exist_ok=True)
    for i in range(1, 4):
        fp = final_dir / f"script_part{i}.json"
        pp = prompts_dir / f"scene_prompts_part{i}.json"
        if not pp.exists():
            r = pipeline._stage_scene_prompts(str(fp), str(scenes_path))
            if r.success:
                print(f"  ✅ 第{i}段HyDE镜头提示: {pp.name}")
            else:
                print(f"  ⚠️  镜头提示失败: {r.error}")
        else:
            print(f"  ✅ 使用已有: {pp.name}")

    # ── Stage 9: 渲染清单 ─────────────────────────────────────────────
    manifest_path = actual_work_dir / "render_manifest.json"
    final_paths = [str(final_dir / f"script_part{i}.json") for i in range(1, 4)]
    prompt_paths = [str(prompts_dir / f"scene_prompts_part{i}.json") for i in range(1, 4)]

    if not manifest_path.exists():
        r = pipeline._stage_render_manifest(final_paths, prompt_paths, str(scenes_path))
        if r.success:
            print(f"  ✅ 渲染清单: {r.output_path}")
            Path(str(r.output_path) + ".done").touch()
        else:
            print(f"  ❌ 渲染清单失败: {r.error}")
            return
    else:
        print(f"  ✅ 使用已有: {manifest_path}")

    # ── 展示渲染清单内容 ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("📄 render_manifest.json 内容预览")
    print("="*60)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"\n视频分段: {len(manifest.get('parts', []))} 段")
    print(f"编码器: {manifest.get('global', {}).get('video_codec', 'N/A')}")
    print(f"分辨率: {manifest.get('global', {}).get('resolution', 'N/A')}")

    for part in manifest.get("parts", []):
        print(f"\n  📹 第{part['part_num']}段:")
        print(f"     配音: {part.get('narration_audio', 'N/A')}")
        print(f"     字幕: {part.get('subtitle_file', 'N/A')}")
        print(f"     输出: {part.get('output_file', 'N/A')}")
        for sent in part.get("sentences", [])[:2]:
            print(f"     [{sent['sentence_id']}] {sent['text'][:40]}... (~{sent['estimated_dur']}s)")

    # ── RAG 知识库演示 ─────────────────────────────────────────────────
    print("\n" + "="*60)
    print("🗃️  RAG 知识库演示")
    print("="*60)
    kb = KnowledgeBase()

    hooks = kb.retrieve_hook("悬疑 电影 反转", style="悬疑反转", top_k=3)
    print(f"\n检索 '悬疑 电影 反转' (top=3):")
    for h in hooks:
        print(f"  [{h['id']}] {h['text'][:50]}... (CTR: {h.get('avg_ctr', 'N/A')})")

    titles = kb.retrieve_title("反转 结局 震撼", style="悬疑反转", top_k=3)
    print(f"\n检索 '反转 结局 震撼' (top=3):")
    for t in titles:
        print(f"  [{t['id']}] {t['text'][:50]}... (播放: {t.get('views', 'N/A')})")

    rule = kb.get_pacing_rule("悬疑反转")
    if rule:
        print(f"\n悬疑反转节奏规则:")
        print(f"  {rule.get('rule', '')[:100]}")

    print("\n" + "="*60)
    print("✅ 完整流水线演示完成!")
    print(f"📁 输出目录: {WORK_DIR}")
    print("="*60)

    # 列出所有输出文件
    print("\n📂 生成的中间文件:")
    for f in sorted(WORK_DIR.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"  {f.relative_to(WORK_DIR)} ({size} bytes)")


if __name__ == "__main__":
    run_with_mock()
