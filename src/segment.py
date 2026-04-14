"""
src/segment.py - PySceneDetect 镜头切分检测
────────────────────────────────────────────
输入: movie_path
输出: work_dir/scenes.json
      时间戳格式: "HH:MM:SS"
"""

import json
from pathlib import Path
from typing import Any, Dict


def run(context: Dict[str, Any], work_dir: Path) -> None:
    """主入口: PySceneDetect 镜头检测 → scenes.json"""
    movie_path = context["movie_path"]
    output_path = work_dir / "scenes.json"

    if output_path.exists():
        print(f"  scenes.json 已存在，跳过")
        return

    print(f"  电影: {movie_path}")

    try:
        from scenedetect import SceneManager, VideoManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        raise RuntimeError("scenedetect not installed: pip install scenedetect")

    # PySceneDetect 0.6.x API: VideoManager([path])
    video_mgr = VideoManager([movie_path])
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=30.0))
    video_mgr.start()

    # 注意: scenedetect 0.6.x 用 detect_scenes(video_mgr) 而非 frame_source=
    sm.detect_scenes(video_mgr)
    scenes = sm.get_scene_list()
    video_mgr.release()

    # 转换格式
    result_scenes = []
    for i, scene in enumerate(scenes):
        start = scene[0].get_timecode()   # FrameTimecode
        end   = scene[1].get_timecode()
        result_scenes.append({
            "scene_id": i + 1,
            "start":    str(start),         # "HH:MM:SS"
            "end":      str(end),
            "description": "",
        })

    result = {"scenes": result_scenes}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 镜头检测完成: {len(result_scenes)} 个镜头 → {output_path}")
