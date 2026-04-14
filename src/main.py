"""
src/main.py - 电影自动浓缩解说系统 - 主入口
──────────────────────────────────────────────
用法:
  python src/main.py <movie_path> [start_from_stage]
  python src/main.py input/film.mp4
  python src/main.py input/film.mp4 segment   # 从镜头检测开始

环境变量:
  OLLAMA_BASE        Ollama 地址 (默认: http://localhost:11434/v1)
  DEEPSEEK_API_KEY   DeepSeek API Key
  OPENAI_API_KEY     MiniMax API Key (OPENAI_API_KEY 格式)
  OPENAI_API_BASE    MiniMax API Base (默认: https://api.minimax.chat/v1)
  MAX_RETRIES        最大重试次数 (默认: 3)
"""

import os
import sys
import argparse
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.task_manager import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="电影自动浓缩解说系统")
    parser.add_argument("movie", help="电影文件路径")
    parser.add_argument("start_from", nargs="?", default=None,
                        help="从指定 stage 开始 (用于断点续跑)")
    parser.add_argument("--work-dir", "-w", default=None,
                        help="指定工作目录 (默认: work/<电影名>/)")

    args = parser.parse_args()

    # 检查电影文件存在
    movie_path = Path(args.movie)
    if not movie_path.exists():
        print(f"❌ 电影文件不存在: {movie_path}")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════╗
║     🎬 电影自动浓缩解说系统 v3.0                     ║
╠══════════════════════════════════════════════════════╣
║  电影: {str(movie_path):<44}║
║  起始: {args.start_from or '从头开始':<44}║
╚══════════════════════════════════════════════════════╝
""")

    # 打印配置
    print("📋 配置检查:")
    has_ollama   = os.getenv("OLLAMA_BASE", "http://localhost:11434/v1")
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    has_minimax  = bool(os.getenv("OPENAI_API_KEY"))
    print(f"  Ollama:   {'✅ ' + has_ollama if has_ollama else '⚠️  未配置'}")
    print(f"  DeepSeek: {'✅ 已配置' if has_deepseek else '⚠️  未配置'}")
    print(f"  MiniMax:  {'✅ 已配置' if has_minimax else '⚠️  未配置'}")
    print()

    try:
        run_pipeline(str(movie_path), args.start_from)
    except Exception as e:
        print(f"\n❌ 流水线失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
