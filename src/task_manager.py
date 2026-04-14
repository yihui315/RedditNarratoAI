"""
src/task_manager.py - 任务调度器：断点续跑 + 重试
──────────────────────────────────────────────────
设计原则:
  1. 所有中间结果落盘，不走内存
  2. 每个 stage 独立可运行
  3. status.json 记录已完成的 stage
  4. 每个 stage 最多重试 MAX_RETRIES 次
"""

import os
import json
import time
import importlib
from pathlib import Path
from typing import Optional, Dict, Any

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "2"))


def get_work_dir(movie_path: str) -> Path:
    """根据电影文件生成工作目录"""
    name = Path(movie_path).stem  # e.g. "film.mp4" → "film"
    work_root = Path("work")
    work_root.mkdir(exist_ok=True)
    wd = work_root / name
    wd.mkdir(exist_ok=True)
    return wd


def get_status_file(work_dir: Path) -> Path:
    return work_dir / "status.json"


def load_status(work_dir: Path) -> Dict[str, str]:
    """加载状态文件"""
    sf = get_status_file(work_dir)
    if sf.exists():
        return json.loads(sf.read_text(encoding="utf-8"))
    return {}


def save_status(work_dir: Path, status: Dict[str, str]) -> None:
    """保存状态文件"""
    sf = get_status_file(work_dir)
    sf.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")


def is_stage_done(work_dir: Path, stage: str) -> bool:
    """检查 stage 是否已完成"""
    status = load_status(work_dir)
    return status.get(stage) == "done"


def mark_done(work_dir: Path, stage: str) -> None:
    """标记 stage 为完成"""
    status = load_status(work_dir)
    status[stage] = "done"
    save_status(work_dir, status)


def mark_failed(work_dir: Path, stage: str, error: str) -> None:
    """标记 stage 为失败"""
    status = load_status(work_dir)
    status[stage] = f"failed: {error}"
    save_status(work_dir, status)


# ── Stage 执行 ─────────────────────────────────────────────────────────────

def run_stage(
    stage: str,
    context: Dict[str, Any],
    work_dir: Optional[Path] = None,
) -> None:
    """
    执行单个 stage，带断点续跑和重试

    Args:
        stage:    stage 名称 (e.g. "transcribe", "segment")
        context:  上下文 dict，包含 movie_path 等
        work_dir: 工作目录，默认从 movie_path 推断

    Raises:
        RuntimeError: 所有重试都失败
    """
    if work_dir is None:
        work_dir = get_work_dir(context["movie_path"])

    # ── 断点检查 ──────────────────────────────────────────────────────────
    if is_stage_done(work_dir, stage):
        print(f"  ⏭️  [{stage}] 已完成，跳过")
        return

    # ── 重试循环 ──────────────────────────────────────────────────────────
    for attempt in range(MAX_RETRIES):
        try:
            print(f"\n  ▶️  [{stage}] 第 {attempt+1} 次尝试...")

            # 动态导入 stage 模块
            module = importlib.import_module(f"src.{stage}")
            module.run(context, work_dir)

            # 成功，标记并返回
            mark_done(work_dir, stage)
            print(f"  ✅ [{stage}] 完成")
            return

        except Exception as e:
            print(f"  ⚠️  [{stage}] 失败: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"  ⏳ {RETRY_DELAY}秒后重试...")
                time.sleep(RETRY_DELAY)
            else:
                mark_failed(work_dir, stage, str(e))
                raise RuntimeError(f"Stage '{stage}' failed after {MAX_RETRIES} retries: {e}") from e


# ── 全流程执行 ─────────────────────────────────────────────────────────────

STAGES_ORDER = [
    "transcribe",
    "segment",
    "chapter_draft",
    "chapter_refine",
    "outline",
    "script",
    "reflect",
    "repair",
    "scene_prompt_draft",
    "scene_prompt_refine",
    "tts",
    "subtitle",
    "render_manifest",
    "render_video",
]


def run_pipeline(movie_path: str, start_from: Optional[str] = None) -> None:
    """
    运行完整流水线

    Args:
        movie_path:  电影文件路径
        start_from:  可选，从指定 stage 开始（用于断点续跑）
    """
    work_dir = get_work_dir(movie_path)
    context = {"movie_path": movie_path, "work_dir": str(work_dir)}

    print(f"📁 工作目录: {work_dir}")

    # 确定起始 stage
    stages = STAGES_ORDER
    if start_from:
        if start_from not in stages:
            raise ValueError(f"Unknown stage: {start_from}")
        stages = stages[stages.index(start_from):]

    for stage in stages:
        print(f"\n{'='*60}")
        print(f"=== Stage: {stage}")
        print(f"{'='*60}")
        run_stage(stage, context, work_dir)

    print(f"\n🎉 ALL DONE! 输出在: {work_dir}")


# ── CLI 入口 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    movie_path = sys.argv[1] if len(sys.argv) > 1 else "input/film.mp4"
    start_from = sys.argv[2] if len(sys.argv) > 2 else None
    run_pipeline(movie_path, start_from)
