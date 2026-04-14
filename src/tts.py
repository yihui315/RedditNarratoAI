"""
src/tts.py - Edge TTS 文本转语音
─────────────────────────────────
输入: final_scripts/final_{part}.json
输出: work_dir/audio/audio_part{N}.mp3

使用 Edge (Azure) TTS，免费的优质中文语音
"""

import json
import asyncio
from pathlib import Path
from typing import Any, Dict

import edge_tts


# 语音配置
VOICE_MAP = {
    "part1": "zh-CN-XiaoxiaoNeural",   # 开头女声，活泼
    "part2": "zh-CN-XiaoyiNeural",     # 中段女声，温和
    "part3": "zh-CN-YunxiNeural",      # 结尾男声，有力
}

RATE = "+0%"      # 语速
PITCH = "+0Hz"    # 音调


async def _generate_audio(text: str, output_path: str, voice: str) -> None:
    """异步生成MP3"""
    communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    await communicate.save(output_path)


def _build_ssml(paragraph_text: str) -> str:
    """构建带节奏标注的SSML（可选，用于精细控制）"""
    return f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='zh-CN'>
    <voice name='zh-CN-XiaoxiaoNeural'>{paragraph_text}</voice>
</speak>"""


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口"""
    final_dir  = work_dir / "final_scripts"
    audio_dir  = work_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    for part_name in ["part1", "part2", "part3"]:
        script_path = final_dir / f"final_{part_name}.json"
        audio_path  = audio_dir / f"audio_{part_name.replace('part', 'part')}.mp3"

        if audio_path.exists():
            print(f"  audio_{part_name}.mp3 已存在，跳过")
            continue

        if not script_path.exists():
            print(f"  ⚠️  {script_path} 不存在，跳过")
            continue

        script = json.loads(script_path.read_text(encoding="utf-8"))
        paragraph_text = " ".join(s["text"] for s in script.get("sentences", []))

        if not paragraph_text.strip():
            print(f"  ⚠️  {part_name} 文本为空，跳过")
            continue

        voice = VOICE_MAP.get(part_name, "zh-CN-XiaoxiaoNeural")
        print(f"  生成 {part_name} 配音: {voice}...")

        try:
            asyncio.run(_generate_audio(paragraph_text, str(audio_path), voice))
            size = audio_path.stat().st_size
            print(f"  ✅ {part_name}: {size/1024:.1f}KB → {audio_path}")
        except Exception as e:
            print(f"  ❌ {part_name} TTS失败: {e}")
            raise
