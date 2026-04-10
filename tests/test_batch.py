"""
测试批量处理引擎
"""

import os
import pytest
import tempfile
from app.batch import BatchProcessor, BatchSummary


class TestBatchProcessor:
    """测试批量处理器"""

    def test_load_urls_from_file(self):
        """测试从文件加载 URL"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("https://reddit.com/r/test/comments/abc123\n")
            f.write("# 这是注释\n")
            f.write("https://reddit.com/r/test/comments/def456\n")
            f.write("\n")  # 空行
            f.write("https://reddit.com/r/test/comments/ghi789\n")
            tmp_path = f.name

        try:
            urls = BatchProcessor.load_urls_from_file(tmp_path)
            assert len(urls) == 3
            assert urls[0] == "https://reddit.com/r/test/comments/abc123"
            assert urls[1] == "https://reddit.com/r/test/comments/def456"
            assert urls[2] == "https://reddit.com/r/test/comments/ghi789"
        finally:
            os.unlink(tmp_path)

    def test_load_urls_ignores_comments(self):
        """测试忽略注释行"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("# 注释\n")
            f.write("  \n")
            f.write("https://reddit.com/r/test/comments/abc\n")
            tmp_path = f.name

        try:
            urls = BatchProcessor.load_urls_from_file(tmp_path)
            assert len(urls) == 1
        finally:
            os.unlink(tmp_path)


class TestBatchSummary:
    """测试批处理汇总"""

    def test_success_rate(self):
        summary = BatchSummary(total=10, success=8, failed=2)
        assert summary.success_rate == 80.0

    def test_empty_summary(self):
        summary = BatchSummary()
        assert summary.success_rate == 0

    def test_str_format(self):
        summary = BatchSummary(total=2, success=1, failed=1)
        text = str(summary)
        assert "批量处理汇总" in text
        assert "50.0%" in text
