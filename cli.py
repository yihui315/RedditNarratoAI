#!/usr/bin/env python3
"""
RedditNarratoAI CLI
命令行入口，支持:
  - Reddit视频流水线（原有功能）
  - 短剧解说全自动Agent流水线（新功能）

用法:
  # 全自动短剧解说（搜索YouTube关键词）
  python cli.py agent --keywords "short drama revenge"

  # 全自动短剧解说（指定视频URL）
  python cli.py agent --url "https://youtube.com/watch?v=xxx"

  # 批量模式
  python cli.py agent --keywords "短剧 逆袭" --max-videos 5

  # 原有Reddit流水线
  python cli.py reddit --url "https://reddit.com/r/..."
"""

import argparse
import json
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

    args = parser.parse_args()

    if args.command == "agent":
        cmd_agent(args)
    elif args.command == "reddit":
        cmd_reddit(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
