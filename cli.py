#!/usr/bin/env python3
"""
RedditNarratoAI CLI
命令行入口，支持:
  - Reddit视频流水线（原有功能）
  - 短剧解说全自动Agent流水线（新功能）
  - 交互式配置向导（新功能）

用法:
  # 全自动短剧解说（搜索YouTube关键词）
  python cli.py agent --keywords "short drama revenge"

  # 全自动短剧解说（指定视频URL）
  python cli.py agent --url "https://youtube.com/watch?v=xxx"

  # 批量模式
  python cli.py agent --keywords "短剧 逆袭" --max-videos 5

  # 原有Reddit流水线（支持风格选择）
  python cli.py reddit --url "https://reddit.com/r/..." --style suspense

  # 交互式配置向导
  python cli.py setup

  # 环境自检
  python cli.py check
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
    style = getattr(args, "style", "shock")

    def progress(step, pct):
        print(f"  [{pct}%] {step}")

    result = run_pipeline(
        reddit_url=args.url,
        config_dict=config,
        progress_callback=progress,
        style=style,
    )

    if result.success:
        print(f"\n✅ 视频生成成功: {result.video_path}")
    else:
        print(f"\n❌ 失败: {result.error}")
        sys.exit(1)


def cmd_setup(_args):
    """交互式配置向导"""
    import toml
    from pathlib import Path

    config_path = Path(__file__).parent / "config.toml"
    example_path = Path(__file__).parent / "config.example.toml"

    print("\n🔧 RedditNarratoAI 配置向导")
    print("=" * 50)

    # Load existing or example config
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = toml.load(f)
        print("  📄 已有 config.toml，将在此基础上更新\n")
    elif example_path.exists():
        with open(example_path, "r", encoding="utf-8") as f:
            cfg = toml.load(f)
        print("  📄 从 config.example.toml 创建新配置\n")
    else:
        cfg = {}

    # --- LLM ---
    print("── LLM 配置 ──")
    llm = cfg.setdefault("llm", {})
    provider = input(f"  LLM提供商 (openai/ollama/azure) [{llm.get('provider', 'openai')}]: ").strip()
    if provider:
        llm["provider"] = provider
    api_base = input(f"  API地址 [{llm.get('api_base', 'http://localhost:11434/v1')}]: ").strip()
    if api_base:
        llm["api_base"] = api_base
    model = input(f"  模型名称 [{llm.get('model', 'deepseek-r1:32b')}]: ").strip()
    if model:
        llm["model"] = model
    api_key = input(f"  API Key [{llm.get('api_key', 'not-needed')}]: ").strip()
    if api_key:
        llm["api_key"] = api_key

    # --- TTS ---
    print("\n── TTS 语音配置 ──")
    tts = cfg.setdefault("tts", {})
    voice = input(f"  语音 [{tts.get('voice', 'zh-CN-XiaoxiaoNeural')}]: ").strip()
    if voice:
        tts["voice"] = voice

    # --- Video ---
    print("\n── 视频输出 ──")
    video = cfg.setdefault("video", {})
    aspect = input(f"  画面比例 (landscape/portrait/square) [{video.get('aspect', '')}]: ").strip()
    if aspect:
        video["aspect"] = aspect

    # --- Style ---
    print("\n── 文案风格 ──")
    print("  可选: suspense(悬疑), humor(搞笑), shock(震惊), warm(温情), educational(科普)")
    style_cfg = cfg.setdefault("style", {})
    style = input(f"  默认风格 [{style_cfg.get('default', 'shock')}]: ").strip()
    if style:
        style_cfg["default"] = style

    # --- Reddit (optional) ---
    print("\n── Reddit API (可选，仅Reddit流水线需要) ──")
    setup_reddit = input("  是否配置Reddit API? (y/N): ").strip().lower()
    if setup_reddit == "y":
        reddit = cfg.setdefault("reddit", {})
        creds = reddit.setdefault("creds", {})
        for field_name in ["client_id", "client_secret", "username", "password"]:
            val = input(f"  {field_name} [{creds.get(field_name, '')}]: ").strip()
            if val:
                creds[field_name] = val

    # Save
    with open(config_path, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)

    print(f"\n✅ 配置已保存到: {config_path}")
    print("  运行 `python cli.py check` 验证环境")


def cmd_check(_args):
    """环境自检"""
    print("\n🔍 RedditNarratoAI 环境检查")
    print("=" * 50)
    all_ok = True

    # Python
    print(f"  ✅ Python {sys.version.split()[0]}")

    # FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"  ✅ FFmpeg: {ffmpeg_path}")
    else:
        print("  ❌ FFmpeg: 未找到！请安装 ffmpeg")
        all_ok = False

    # config.toml
    from pathlib import Path
    config_path = Path(__file__).parent / "config.toml"
    if config_path.exists():
        print(f"  ✅ config.toml 存在")
    else:
        print("  ⚠️  config.toml 不存在，运行 `python cli.py setup` 创建")
        all_ok = False

    # LLM connectivity
    try:
        cfg = load_config()
        llm = cfg.get("llm", {})
        api_base = llm.get("api_base", "")
        if api_base:
            import urllib.request
            host = api_base.rstrip("/")
            # Just check if the host is reachable (GET /v1/models or similar)
            try:
                req = urllib.request.Request(f"{host}/models", method="GET")
                urllib.request.urlopen(req, timeout=5)
                print(f"  ✅ LLM API ({host}): 连接成功")
            except Exception:
                print(f"  ⚠️  LLM API ({host}): 无法连接（请确认服务已启动）")
    except Exception:
        pass

    # Edge TTS
    try:
        import edge_tts
        print(f"  ✅ Edge TTS: 已安装")
    except ImportError:
        print("  ❌ Edge TTS: 未安装 (pip install edge-tts)")
        all_ok = False

    # MoviePy
    try:
        import moviepy
        print(f"  ✅ MoviePy: {moviepy.__version__}")
    except ImportError:
        print("  ❌ MoviePy: 未安装")
        all_ok = False

    print()
    if all_ok:
        print("  🎉 环境检查通过！")
    else:
        print("  ⚠️  部分组件缺失，请按提示安装")


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
    reddit_parser.add_argument(
        "--style", "-s",
        choices=["suspense", "humor", "shock", "warm", "educational"],
        default="shock",
        help="文案风格 (默认shock/震惊)",
    )

    # ---- setup子命令 ----
    subparsers.add_parser(
        "setup",
        help="交互式配置向导",
    )

    # ---- check子命令 ----
    subparsers.add_parser(
        "check",
        help="环境自检（FFmpeg、LLM连接等）",
    )

    args = parser.parse_args()

    if args.command == "agent":
        cmd_agent(args)
    elif args.command == "reddit":
        cmd_reddit(args)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
