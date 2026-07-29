#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件系统工具函数"""

from pathlib import Path


def format_bytes_size(bytes_size: int) -> str:
    """格式化文件大小

    Args:
        bytes_size: 文件大小（字节）

    Returns:
        格式化后的大小字符串，如 '1.5 MB'
    """
    if bytes_size < 1024:
        return f"{bytes_size} B"
    if bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    if bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


def ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则创建

    Args:
        path: 目录路径

    Returns:
        目录 Path 对象
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_rename_path(src: Path, dst: Path) -> None:
    """安全重命名/移动文件路径

    若目标已存在则先删除，再重命名。

    Args:
        src: 源路径
        dst: 目标路径
    """
    if dst.exists():
        dst.unlink()
    src.rename(dst)
