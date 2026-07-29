#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相册服务模块 - 封装相册相关业务逻辑
遵循单一职责原则：仅负责相册的业务逻辑处理
使用SQLite数据库存储，不再使用JSON文件
"""

import os
import random
import shutil

from pathlib import Path
from typing import Dict, Any, Optional

from config import DATA_DIR, PREVIEW_DIR
from constants import ALBUM_COLORS
from db import (
    create_album, get_album_by_id, get_album_by_name,
    get_all_albums, get_summary,
    create_tag, get_tag_by_name, get_tag_by_id,
    get_all_tags, cleanup_unused_tags,
    rename_album_records, delete_album_records,
)


class AlbumService:
    """相册服务类"""

    def __init__(self):
        self.colors = ALBUM_COLORS

    def get_random_color(self) -> str:
        """获取随机颜色"""
        return random.choice(self.colors)

    def load_summary(self) -> Dict[str, Any]:
        """加载相册概览数据（从数据库）"""
        return get_summary()

    def create_album(self, name: str) -> int:
        """创建新相册

        Args:
            name: 相册名称

        Returns:
            album_id: 新相册的ID

        Raises:
            ValueError: 相册名称为空或已存在
        """
        db_album_id = create_album(name)
        return db_album_id

    def rename_album(self, album_id, new_name: str) -> int:
        """重命名相册（DB 记录 + 物理文件 + 预览文件）

        Args:
            album_id: 相册ID（可能是数字字符串或escaped_name）
            new_name: 新相册名称

        Returns:
            new_album_id: 新相册的ID

        Raises:
            ValueError: 相册不存在或名称无效
        """
        album_info = self._resolve_album_id(album_id)
        if not album_info:
            raise ValueError("相册不存在")

        db_album_id = album_info['id']
        old_name = album_info['name']
        if new_name == old_name:
            return db_album_id

        # 1) 先更新 DB 记录（事务），返回旧名/新名/照片列表
        result = rename_album_records(db_album_id, new_name)
        if result.get('skipped'):
            return db_album_id

        old_name = result['old_name']
        new_name = result['new_name']
        photos = result['photos']

        # 2) 再执行文件系统重命名（DB 已提交，FS 失败需手动回滚报错）
        self._rename_album_files(old_name, new_name, photos)

        return db_album_id

    def _rename_album_files(self, old_name: str, new_name: str, photos: list) -> None:
        """重命名相册的物理目录与预览文件"""
        old_data_dir = DATA_DIR / old_name
        new_data_dir = DATA_DIR / new_name

        if not old_data_dir.exists():
            return

        if new_data_dir.exists():
            shutil.rmtree(str(new_data_dir))

        try:
            os.rename(str(old_data_dir), str(new_data_dir))
        except OSError as e:
            raise ValueError(f"文件夹重命名失败: {str(e)}")

    def delete_album(self, album_id) -> None:
        """删除相册（DB 记录 + 物理目录 + 预览文件）

        Args:
            album_id: 相册ID（可能是数字字符串或escaped_name）

        Raises:
            ValueError: 相册不存在
        """
        album_info = self._resolve_album_id(album_id)
        if not album_info:
            raise ValueError("相册不存在")

        db_album_id = album_info['id']

        # 1) 先删除 DB 记录（事务），返回相册名和照片列表
        result = delete_album_records(db_album_id)
        name = result['name']
        photos = result['photos']

        # 2) 再清理物理文件（DB 已提交，FS 失败不影响数据一致性）
        self._delete_album_files(name, photos)

    def _delete_album_files(self, name: str, photos: list) -> None:
        """删除相册的物理目录与所有预览文件"""
        album_dir = DATA_DIR / name
        if album_dir.exists():
            shutil.rmtree(str(album_dir))

        for photo in photos:
            for ext in ['.webp', '.jpg']:
                preview_path = PREVIEW_DIR / f"{photo['album_id']}_{photo['id']}{ext}"
                if preview_path.exists():
                    preview_path.unlink()

    def _resolve_album_id(self, album_id: str) -> Optional[Dict[str, Any]]:
        """解析相册ID，支持数字ID和name

        Args:
            album_id: 相册标识（数字字符串或name）

        Returns:
            相册信息字典，不存在返回None
        """
        try:
            numeric_id = int(album_id)
            return get_album_by_id(numeric_id)
        except ValueError:
            return get_album_by_name(album_id)

    def get_album_by_name(self, name: str) -> Optional[int]:
        """根据名称获取相册ID

        Args:
            name: 相册名称

        Returns:
            album_id: 相册ID，不存在返回None
        """
        album = get_album_by_name(name)
        if album:
            return album['id']
        return None

    def get_album_info(self, album_id: str) -> Optional[Dict[str, Any]]:
        """获取相册信息

        Args:
            album_id: 相册ID（可能是数字字符串或escaped_name）

        Returns:
            相册信息字典，不存在返回None
        """
        album_info = self._resolve_album_id(album_id)
        if album_info:
            return {
                'id': album_info['id'],
                'name': album_info['name'],
                'color': album_info['color']
            }
        return None

    def add_tag_definition(self, tag_name: str) -> bool:
        """添加标签定义

        Args:
            tag_name: 标签名称

        Returns:
            True表示新增了标签，False表示标签已存在
        """
        tag_name = tag_name.strip()
        if not tag_name:
            return False

        tag = get_tag_by_name(tag_name)
        if tag:
            return False

        tag_id = create_tag(tag_name)
        return True

    def cleanup_unused_tags(self) -> None:
        """清理未使用的标签"""
        cleanup_unused_tags()