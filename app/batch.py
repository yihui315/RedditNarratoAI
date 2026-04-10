"""
批量处理引擎
支持多 URL 并行处理，每个 worker 独立运行完整 pipeline
"""

import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from loguru import logger


@dataclass
class BatchResult:
    """单个 URL 的批处理结果"""
    url: str
    success: bool
    video_path: str = ""
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class BatchSummary:
    """批处理汇总"""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: List[BatchResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success / self.total * 100 if self.total > 0 else 0

    def __str__(self):
        lines = [
            "=" * 50,
            "批量处理汇总",
            "=" * 50,
            f"总数: {self.total}",
            f"成功: {self.success}",
            f"失败: {self.failed}",
            f"成功率: {self.success_rate:.1f}%",
            f"总耗时: {self.total_duration_seconds:.1f}s",
            "-" * 50,
        ]
        for r in self.results:
            status = "✅" if r.success else "❌"
            path_info = f" → {r.video_path}" if r.success else f" | {r.error}"
            lines.append(f"{status} {r.url}{path_info} ({r.duration_seconds:.1f}s)")
        lines.append("=" * 50)
        return "\n".join(lines)


def _process_single_url(
    url: str,
    config_dict: dict,
    enable_broll: bool = True,
    enable_bgm: bool = True,
    dry_run: bool = False,
) -> BatchResult:
    """
    处理单个 URL（在子进程中运行）

    Args:
        url: Reddit URL
        config_dict: 配置字典
        enable_broll: 是否启用 B-roll
        enable_bgm: 是否启用 BGM
        dry_run: 仅生成文案

    Returns:
        BatchResult
    """
    start = time.time()
    try:
        from app.pipeline import run_pipeline

        result = run_pipeline(
            reddit_url=url,
            config_dict=config_dict,
            enable_broll=enable_broll,
            enable_bgm=enable_bgm,
            dry_run=dry_run,
        )

        return BatchResult(
            url=url,
            success=result.success,
            video_path=result.video_path,
            error=result.error,
            duration_seconds=time.time() - start,
        )

    except Exception as e:
        return BatchResult(
            url=url,
            success=False,
            error=str(e),
            duration_seconds=time.time() - start,
        )


class BatchProcessor:
    """
    批量处理器

    支持:
    - URL 列表文件输入
    - 命令行多 URL 输入
    - ProcessPoolExecutor 并行
    - 汇总报告
    """

    def __init__(
        self,
        config_dict: dict,
        max_workers: int = 2,
        enable_broll: bool = True,
        enable_bgm: bool = True,
        dry_run: bool = False,
    ):
        self.config = config_dict
        self.max_workers = max_workers
        self.enable_broll = enable_broll
        self.enable_bgm = enable_bgm
        self.dry_run = dry_run

        batch_config = config_dict.get("batch", {})
        if max_workers <= 0:
            self.max_workers = batch_config.get("max_workers", 2)

    def process_urls(
        self,
        urls: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> BatchSummary:
        """
        批量处理 URL 列表

        Args:
            urls: URL 列表
            progress_callback: 进度回调 (completed, total, result)
        """
        summary = BatchSummary(total=len(urls))
        start_time = time.time()

        logger.info(f"开始批量处理: {len(urls)} 个 URL, workers={self.max_workers}")

        # 使用 ProcessPoolExecutor 并行处理
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for url in urls:
                future = executor.submit(
                    _process_single_url,
                    url=url,
                    config_dict=self.config,
                    enable_broll=self.enable_broll,
                    enable_bgm=self.enable_bgm,
                    dry_run=self.dry_run,
                )
                futures[future] = url

            for future in as_completed(futures):
                result = future.result()
                summary.results.append(result)

                if result.success:
                    summary.success += 1
                else:
                    summary.failed += 1

                completed = summary.success + summary.failed
                logger.info(
                    f"[{completed}/{summary.total}] "
                    f"{'✅' if result.success else '❌'} {result.url}"
                )

                if progress_callback:
                    progress_callback(completed, summary.total, result)

        summary.total_duration_seconds = time.time() - start_time
        logger.info(f"\n{summary}")

        return summary

    @staticmethod
    def load_urls_from_file(filepath: str) -> List[str]:
        """从文件加载 URL 列表（每行一个）"""
        urls = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        return urls
