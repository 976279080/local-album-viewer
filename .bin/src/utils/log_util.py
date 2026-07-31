#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志工具模块 - 轻量级日志封装

本地项目使用，输出到文件和可选的控制台。
遵循单一职责原则：仅负责日志初始化与获取。
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from config import BASE_DIR

_log_initialized = False


def init_logging(level: str = 'INFO', log_file: str = None) -> None:
    """初始化日志系统（仅首次调用生效）

    Args:
        level: 日志级别，默认 INFO
        log_file: 日志文件路径，默认 server.log
    """
    global _log_initialized
    if _log_initialized:
        return

    if log_file is None:
        log_file = BASE_DIR / 'server.log'

    log_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 仅在 stdout 可用时添加控制台处理器（pythonw.exe 下 sys.stdout 为 None）
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    _log_initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器

    Args:
        name: 日志器名称，通常使用模块名

    Returns:
        logging.Logger 实例
    """
    if not _log_initialized:
        init_logging()
    return logging.getLogger(name)
