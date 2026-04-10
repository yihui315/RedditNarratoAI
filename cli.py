#!/usr/bin/env python
"""
RedditNarratoAI CLI
Reddit帖子 → AI影视解说视频 命令行工具

用法:
  python cli.py single <reddit_url>          # 单个视频
  python cli.py batch <urls_file_or_url> ... # 批量处理
  python cli.py batch urls.txt               # 从文件批量处理

选项:
  --output-dir PATH        输出目录
  --workers N              并行 worker 数（默认 2）
  --no-broll               禁用 B-roll
  --no-bgm                 禁用背景音乐
  --voice VOICE_NAME       指定 TTS 声音
  --model MODEL_NAME       指定 LLM 模型
  --dry-run                只生成文案不合成视频
"""

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

import click
from loguru import logger

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


def _load_config(output_dir=None, voice=None, model=None):
    """加载并覆盖配置"""
    import toml

    config_path = Path(__file__).parent / "config.toml"
    if config_path.exists():
        config_dict = toml.load(str(config_path))
    else:
        config_dict = {}

    # 命令行参数覆盖
    if output_dir:
        config_dict.setdefault("video", {})["output_dir"] = output_dir
    if voice:
        config_dict.setdefault("tts", {})["voice"] = voice
    if model:
        config_dict.setdefault("llm", {})["model"] = model

    return config_dict


def _print_result(result):
    """打印流水线结果"""
    if RICH_AVAILABLE and console:
        if result.success:
            console.print(Panel(
                f"[bold green]✅ 视频生成成功![/]\n\n"
                f"📹 视频: {result.video_path}\n"
                f"🎵 音频: {result.audio_path}\n"
                f"📝 文案长度: {len(result.script)} 字",
                title="[green]RedditNarratoAI[/]",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[bold red]❌ 处理失败[/]\n\n"
                f"错误: {result.error}",
                title="[red]RedditNarratoAI[/]",
                border_style="red",
            ))

        # 验证日志
        if result.verification_log:
            console.print("\n[bold]验证日志:[/]")
            for log in result.verification_log:
                console.print(log)
    else:
        if result.success:
            print(f"\n✅ 视频生成成功!")
            print(f"  📹 视频: {result.video_path}")
            print(f"  🎵 音频: {result.audio_path}")
            print(f"  📝 文案长度: {len(result.script)} 字")
        else:
            print(f"\n❌ 处理失败: {result.error}")


@click.group()
@click.version_option(version="2.0.0", prog_name="RedditNarratoAI")
def cli():
    """🎬 RedditNarratoAI - Reddit帖子转AI影视解说视频"""
    pass


@cli.command()
@click.argument("reddit_url")
@click.option("--output-dir", "-o", default=None, help="输出目录")
@click.option("--no-broll", is_flag=True, help="禁用 B-roll")
@click.option("--no-bgm", is_flag=True, help="禁用背景音乐")
@click.option("--voice", default=None, help="TTS 声音名称")
@click.option("--model", default=None, help="LLM 模型名称")
@click.option("--dry-run", is_flag=True, help="只生成文案不合成视频")
def single(reddit_url, output_dir, no_broll, no_bgm, voice, model, dry_run):
    """处理单个 Reddit URL 生成视频"""
    config_dict = _load_config(output_dir, voice, model)

    if RICH_AVAILABLE and console:
        console.print(Panel(
            f"🔗 URL: {reddit_url}\n"
            f"🎬 B-roll: {'禁用' if no_broll else '启用'}\n"
            f"🎵 BGM: {'禁用' if no_bgm else '启用'}\n"
            f"📝 Dry run: {'是' if dry_run else '否'}",
            title="[bold blue]RedditNarratoAI[/]",
            border_style="blue",
        ))
    else:
        print(f"\n🎬 RedditNarratoAI")
        print(f"  URL: {reddit_url}")

    from app.pipeline import run_pipeline

    def progress_cb(step, percent):
        if RICH_AVAILABLE and console:
            console.print(f"  [{percent:3d}%] {step}")
        else:
            print(f"  [{percent:3d}%] {step}")

    result = run_pipeline(
        reddit_url=reddit_url,
        config_dict=config_dict,
        progress_callback=progress_cb,
        enable_broll=not no_broll,
        enable_bgm=not no_bgm,
        dry_run=dry_run,
    )

    _print_result(result)

    if result.dry_run if hasattr(result, 'dry_run') else dry_run:
        if result.script:
            print("\n📝 生成的文案:")
            print("-" * 40)
            print(result.script)
            print("-" * 40)

    sys.exit(0 if result.success else 1)


@cli.command()
@click.argument("sources", nargs=-1, required=True)
@click.option("--output-dir", "-o", default=None, help="输出目录")
@click.option("--workers", "-w", default=2, help="并行 worker 数")
@click.option("--no-broll", is_flag=True, help="禁用 B-roll")
@click.option("--no-bgm", is_flag=True, help="禁用背景音乐")
@click.option("--voice", default=None, help="TTS 声音名称")
@click.option("--model", default=None, help="LLM 模型名称")
@click.option("--dry-run", is_flag=True, help="只生成文案不合成视频")
def batch(sources, output_dir, workers, no_broll, no_bgm, voice, model, dry_run):
    """批量处理多个 Reddit URL

    SOURCES 可以是 URL 列表或包含 URL 的文本文件路径
    """
    config_dict = _load_config(output_dir, voice, model)

    # 解析 URLs
    urls = []
    for source in sources:
        if os.path.isfile(source):
            from app.batch import BatchProcessor
            file_urls = BatchProcessor.load_urls_from_file(source)
            urls.extend(file_urls)
            logger.info(f"从文件 {source} 加载 {len(file_urls)} 个 URL")
        else:
            urls.append(source)

    if not urls:
        click.echo("❌ 未提供任何有效的 URL", err=True)
        sys.exit(1)

    if RICH_AVAILABLE and console:
        console.print(Panel(
            f"📋 URL 数量: {len(urls)}\n"
            f"👷 Workers: {workers}\n"
            f"🎬 B-roll: {'禁用' if no_broll else '启用'}\n"
            f"🎵 BGM: {'禁用' if no_bgm else '启用'}",
            title="[bold blue]批量处理[/]",
            border_style="blue",
        ))
    else:
        print(f"\n🎬 批量处理: {len(urls)} 个 URL, workers={workers}")

    from app.batch import BatchProcessor

    processor = BatchProcessor(
        config_dict=config_dict,
        max_workers=workers,
        enable_broll=not no_broll,
        enable_bgm=not no_bgm,
        dry_run=dry_run,
    )

    summary = processor.process_urls(urls)

    # 打印汇总
    if RICH_AVAILABLE and console:
        table = Table(title="批量处理结果")
        table.add_column("状态", style="bold")
        table.add_column("URL")
        table.add_column("视频/错误")
        table.add_column("耗时")

        for r in summary.results:
            status = "[green]✅[/]" if r.success else "[red]❌[/]"
            info = r.video_path if r.success else r.error[:50]
            table.add_row(status, r.url[:60], info, f"{r.duration_seconds:.1f}s")

        console.print(table)
        console.print(
            f"\n成功率: {summary.success_rate:.1f}% "
            f"({summary.success}/{summary.total}) "
            f"总耗时: {summary.total_duration_seconds:.1f}s"
        )
    else:
        print(summary)

    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    cli()
