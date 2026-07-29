#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路径与名称校验工具函数"""

from pathlib import Path

from constants import ILLEGAL_FILENAME_CHARS


def get_file_extension(filename: str) -> str:
    """获取文件扩展名（小写）

    Args:
        filename: 文件名

    Returns:
        扩展名（含点号），如 '.jpg'
    """
    return Path(filename).suffix.lower()


def is_image_file(filename: str, allowed_extensions: set) -> bool:
    """检查是否为图片文件

    Args:
        filename: 文件名
        allowed_extensions: 允许的扩展名集合

    Returns:
        True表示是图片文件
    """
    return get_file_extension(filename) in allowed_extensions


def validate_album_name(name: str) -> None:
    """验证相册名称，不允许包含特殊字符

    Args:
        name: 相册名称

    Raises:
        ValueError: 名称为空或包含特殊字符
    """
    if not name or not name.strip():
        raise ValueError("相册名称不能为空")
    found = set(c for c in name if c in ILLEGAL_FILENAME_CHARS)
    if found:
        raise ValueError("相册名称不能包含特殊字符")


def validate_title_chars(title: str) -> None:
    """验证标题不包含文件命名特殊字符

    Args:
        title: 标题文本

    Raises:
        ValueError: 标题包含特殊字符
    """
    found = set(c for c in title if c in ILLEGAL_FILENAME_CHARS)
    if found:
        raise ValueError("标题不能包含特殊字符：/\\:*?\"<>|.")
