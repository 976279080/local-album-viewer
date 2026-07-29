#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片标签服务 - 封装照片标签相关业务逻辑
遵循单一职责原则：仅负责照片标签的批量操作
"""

from typing import Dict, Any, List

from db import (
    get_photo_by_id, batch_add_tags_to_photos, batch_remove_tags_from_photos,
    batch_get_photo_tags, get_db_connection, get_album_by_name, get_photo_by_path,
)
from services._tag_helpers import cleanup_unused_tags


class PhotoTagService:
    """照片标签服务类"""

    def __init__(self, delete_service=None):
        self._delete_service = delete_service

    def batch_tag(self, path_keys: List[str], tags: List[str]) -> Dict[str, Any]:
        """批量打标签（批量操作，避免 N+1 查询）"""
        photo_map = self._batch_parse_path_keys(path_keys)
        if not photo_map:
            return {'updated_count': 0, 'updated': []}

        photo_ids = list(photo_map.values())
        batch_add_tags_to_photos(photo_ids, tags)

        tags_map = batch_get_photo_tags(photo_ids)

        conn = get_db_connection()
        try:
            placeholders = ','.join(['?'] * len(photo_ids))
            cursor = conn.execute(f'SELECT id, update_time FROM photos WHERE id IN ({placeholders})', photo_ids)
            update_times = {row['id']: row['update_time'] for row in cursor.fetchall()}
        finally:
            conn.close()

        updated = []
        for path_key, photo_id in photo_map.items():
            updated.append({
                'path_key': path_key,
                'tags': tags_map.get(photo_id, []),
                'update_time': update_times.get(photo_id),
            })

        return {'updated_count': len(updated), 'updated': updated}

    def batch_clear_tags(self, path_keys: List[str]) -> Dict[str, Any]:
        """批量清空标签（批量操作，避免 N+1 查询）"""
        photo_map = self._batch_parse_path_keys(path_keys)
        if not photo_map:
            return {'updated_count': 0, 'updated': []}

        photo_ids = list(photo_map.values())
        batch_remove_tags_from_photos(photo_ids)
        cleanup_unused_tags()

        conn = get_db_connection()
        try:
            placeholders = ','.join(['?'] * len(photo_ids))
            cursor = conn.execute(f'SELECT id, update_time FROM photos WHERE id IN ({placeholders})', photo_ids)
            update_times = {row['id']: row['update_time'] for row in cursor.fetchall()}
        finally:
            conn.close()

        updated = []
        for path_key, photo_id in photo_map.items():
            updated.append({
                'path_key': path_key,
                'tags': [],
                'update_time': update_times.get(photo_id),
            })

        return {'updated_count': len(updated), 'updated': updated}

    @staticmethod
    def _batch_parse_path_keys(path_keys: List[str]) -> Dict[str, int]:
        """批量解析 path_keys 为 {path_key: photo_id}，复用单连接"""
        photo_map = {}
        album_cache: Dict[str, int] = {}

        conn = get_db_connection()
        try:
            for path_key in path_keys:
                parts = path_key.split('/')
                if len(parts) != 3:
                    continue
                album_name, year, filename = parts

                if album_name not in album_cache:
                    album = get_album_by_name(album_name, conn=conn)
                    album_cache[album_name] = album['id'] if album else None
                album_id = album_cache[album_name]
                if not album_id:
                    continue

                photo = get_photo_by_path(album_id, year, filename, conn=conn)
                if photo:
                    photo_map[path_key] = photo['id']
        finally:
            conn.close()

        return photo_map
