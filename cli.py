#!/usr/bin/env python3
"""
RedditNarratoAI CLI
命令行入口，支持:
  - Reddit视频流水线（原有功能）
  - 短剧解说全自动Agent流水线（新功能）
  - 配置检查

用法:
  # 全自动短剧解说（搜索YouTube关键词）
  python cli.py agent --keywords "short drama revenge"

  # 全自动短剧解说（指定视频URL）
  python cli.py agent --url "https://youtube.com/watch?v=xxx"

  # 批量模式
  python cli.py agent --keywords "短剧 逆袭" --max-videos 5

  # 原有Reddit流水线
  python cli.py reddit --url "https://reddit.com/r/..."

  # 检查配置和环境
  python cli.py config check
"""

import argparse
import json
import os
import shutil
import sys
from loguru import logger

from app.config.config import load_config


def cmd_agent(args):
    """运行全自动短剧解说Agent流水线"""
    from app.agents.orchestrator import AgentOrchestrator

    config = load_config()
    orch = AgentOrchestrator(config)

    # 设置进度回调（CLI直接打印）
    def progress(agent, pct, msg):
        print(f"  [{agent}] {pct}% {msg}")

    orch.set_progress_callback(progress)

    urls = [args.url] if args.url else []
    results = orch.run(
        keywords=args.keywords or "",
        urls=urls,
        max_videos=args.max_videos,
    )

    # 输出汇总
    print("\n" + "=" * 60)
    print("📊 生产结果汇总")
    print("=" * 60)
    success_count = 0
    for i, r in enumerate(results):
        status = "✅" if r.get("success") else "❌"
        title = r.get("title", "未知")
        print(f"  {status} [{i+1}] {title}")
        if r.get("success"):
            success_count += 1
            print(f"      视频: {r.get('video_path', 'N/A')}")
            meta = r.get("metadata", {})
            if meta:
                print(f"      标签: {', '.join(meta.get('tags', []))}")
        else:
            print(f"      失败阶段: {r.get('stage', '?')}")
            print(f"      错误: {r.get('error', '未知错误')}")
    print(f"\n  总计: {success_count}/{len(results)} 成功")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  结果已保存: {args.output_json}")


def cmd_reddit(args):
    """运行Reddit视频流水线"""
    from app.pipeline import run_pipeline

    config = load_config()

    def progress(step, pct):
        print(f"  [{pct}%] {step}")

    result = run_pipeline(
        reddit_url=args.url,
        config_dict=config,
        progress_callback=progress,
    )

    if result.success:
        print(f"\n✅ 视频生成成功: {result.video_path}")
    else:
        print(f"\n❌ 失败: {result.error}")
        sys.exit(1)


def cmd_config_check(args):
    """检查配置和运行环境"""
    print("🔍 RedditNarratoAI 环境检查")
    print("=" * 50)
    errors = []
    warnings = []

    # 1. config.toml
    config_path = os.path.join(os.path.dirname(__file__), "config.toml")
    if os.path.exists(config_path):
        print("✅ config.toml 存在")
        try:
            cfg = load_config()
            print(f"   项目名: {cfg.get('app', {}).get('name', 'N/A')}")
        except Exception as e:
            errors.append(f"config.toml 加载失败: {e}")
            print(f"❌ config.toml 加载失败: {e}")
            cfg = {}
    else:
        errors.append("config.toml 不存在")
        print("❌ config.toml 不存在 — 请复制 config.example.toml 为 config.toml")
        cfg = {}

    # 2. LLM配置
    llm = cfg.get("llm", {})
    if llm.get("provider"):
        print(f"✅ LLM: provider={llm['provider']}, model={llm.get('model', 'N/A')}")
        if llm.get("provider") == "ollama":
            print(f"   Ollama API: {llm.get('api_base', 'N/A')}")
    else:
        warnings.append("[llm] 段未配置")
        print("⚠️  [llm] 段未配置 — Agent模式需要LLM")

    # 3. FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"✅ FFmpeg: {ffmpeg_path}")
    else:
        errors.append("FFmpeg 未安装或不在PATH中")
        print("❌ FFmpeg 未安装 — 视频合成必需")

    # 4. yt-dlp
    ytdlp_path = shutil.which("yt-dlp")
    if ytdlp_path:
        print(f"✅ yt-dlp: {ytdlp_path}")
    else:
        warnings.append("yt-dlp 未安装")
        print("⚠️  yt-dlp 未安装 — Agent模式搜索YouTube需要")

    # 5. Python依赖
    missing_deps = []
    for mod_name, pip_name in [
        ("edge_tts", "edge-tts"),
        ("pysrt", "pysrt"),
        ("moviepy", "moviepy"),
        ("pydub", "pydub"),
        ("openai", "openai"),
        ("toml", "toml"),
        ("streamlit", "streamlit"),
        ("praw", "praw"),
    ]:
        try:
            __import__(mod_name)
        except ImportError:
            missing_deps.append(pip_name)

    if not missing_deps:
        print("✅ Python依赖: 全部已安装")
    else:
        errors.append(f"缺少依赖: {', '.join(missing_deps)}")
        print(f"❌ 缺少Python依赖: {', '.join(missing_deps)}")
        print(f"   运行: pip install {' '.join(missing_deps)}")

    # 6. Output directory
    output_dir = cfg.get("video", {}).get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)
    if os.access(output_dir, os.W_OK):
        print(f"✅ 输出目录: {os.path.abspath(output_dir)}")
    else:
        errors.append(f"输出目录不可写: {output_dir}")
        print(f"❌ 输出目录不可写: {output_dir}")

    # Summary
    print("\n" + "=" * 50)
    if errors:
        print(f"❌ 发现 {len(errors)} 个错误, {len(warnings)} 个警告")
        for e in errors:
            print(f"   ❌ {e}")
        for w in warnings:
            print(f"   ⚠️  {w}")
        sys.exit(1)
    elif warnings:
        print(f"✅ 基本环境正常 ({len(warnings)} 个警告)")
        for w in warnings:
            print(f"   ⚠️  {w}")
    else:
        print("✅ 所有检查通过，环境就绪！")


def main():
    parser = argparse.ArgumentParser(
        description="RedditNarratoAI - AI视频生产CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ---- agent子命令 ----
    agent_parser = subparsers.add_parser(
        "agent",
        help="全自动短剧解说Agent（搜索→分析→文案→配音→剪辑）",
    )
    agent_group = agent_parser.add_mutually_exclusive_group(required=True)
    agent_group.add_argument(
        "--keywords", "-k",
        help='YouTube搜索关键词 (如 "short drama revenge")',
    )
    agent_group.add_argument(
        "--url", "-u",
        help="直接指定YouTube视频URL",
    )
    agent_parser.add_argument(
        "--max-videos", "-n",
        type=int, default=3,
        help="最多处理几条视频 (默认3)",
    )
    agent_parser.add_argument(
        "--output-json", "-o",
        help="将结果保存为JSON文件",
    )

    # ---- reddit子命令 ----
    reddit_parser = subparsers.add_parser(
        "reddit",
        help="Reddit帖子→AI解说视频",
    )
    reddit_parser.add_argument(
        "--url", "-u",
        required=True,
        help="Reddit帖子URL",
    )

    # ---- config子命令 ----
    config_parser = subparsers.add_parser(
        "config",
        help="配置管理",
    )
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("check", help="检查配置和环境")

    args = parser.parse_args()

    if args.command == "agent":
        cmd_agent(args)
    elif args.command == "reddit":
        cmd_reddit(args)
    elif args.command == "config":
        if args.config_action == "check":
            cmd_config_check(args)
        else:
            config_parser.print_help()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
