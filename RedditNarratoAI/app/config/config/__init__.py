import os
import sys

# 简单的logger初始化，不依赖其他模块
_log_level = os.environ.get("LOG_LEVEL", "INFO")

try:
    from loguru import logger
    logger.remove()
    logger.add(
        sys.stdout,
        level=_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</> | <level>{level: <8}</level> | <level>{message}</level>\n"
    )
except ImportError:
    import logging
    logging.basicConfig(level=_log_level, format="%(asctime)s | %(levelname)s | %(message)s")
