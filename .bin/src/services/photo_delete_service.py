#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片删除服务 - 封装照片删除相关业务逻辑
遵循单一职责原则：仅负责照片删除与清理工作
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from config import DATA_DIR, PREVIEW_DIR
from db import (
    get_photo_by_id, get_photo_by_path, get_photos_by_album, count_photos_by_album,
    get_album_by_id, delete_photo_records, batch_delete_photos,
    get_db_connection, get_album_by_name, get_summary,
)
from services._tag_helpers import cleanup_unused_tags


class PhotoDeleteService:
    """照片删除服务类"""

    VACUUM_THRESHOLD = 100  # 每 100 张删除触发一次 VACUUM
    _delete_counter = 0

    def delete_photo(self, path_key_or_id) -> None:
        """删除单张照片

        Args:
            path_key_or_id: 照片路径键（str）或照片ID（int）
        """
        if isinstance(path_key_or_id, int):
            photo = get_photo_by_id(path_key_or_id)
            if not photo:
                raise ValueError("照片不存在")
        else:
            photo = self._parse_path_key(path_key_or_id)
            if not photo:
                raise ValueError("Invalid path")

        album_id = photo['album_id']
        year = photo['year']
        photo_id = photo['id']

        info = delete_photo_records(photo_id)

        self._cleanup_photo_files(info['album_name'], info['year'], info['filename'], album_id, photo_id)

        cleanup_unused_tags()
        self._cleanup_empty_year(album_id, year)
        self._cleanup_empty_album(album_id)

        self._maybe_vacuum(1)

    def batch_delete(self, path_keys: List[str]) -> Dict[str, Any]:
        """批量删除照片（DB + 文件系统，分阶段执行）"""
        collected = self._collect_photos_for_batch_delete(path_keys)
        if not collected['photo_ids']:
            return {'deleted_count': 0, 'deleted_path_keys': []}

        self._batch_delete_db_records(collected['photo_ids'])
        self._batch_delete_files(collected['files_to_delete'])

        for album_id, years in collected['affected_years'].items():
            for year in years:
                self._cleanup_empty_year(album_id, year)
            self._cleanup_empty_album(album_id)

        deleted_count = len(collected['deleted_path_keys'])
        self._maybe_vacuum(deleted_count)

        return {
            'deleted_count': deleted_count,
            'deleted_path_keys': collected['deleted_path_keys'],
        }

    @classmethod
    def _maybe_vacuum(cls, count: int) -> None:
        """累积删除数量达到阈值时执行 VACUUM，避免频繁重写数据库"""
        cls._delete_counter += count
        if cls._delete_counter >= cls.VACUUM_THRESHOLD:
            cls._vacuum_database()
            cls._delete_counter = 0

    @staticmethod
    def _vacuum_database() -> None:
        """执行 VACUUM 回收 SQLite 未使用的磁盘空间"""
        try:
            conn = get_db_connection()
            try:
                conn.execute('VACUUM')
            finally:
                conn.close()
        except Exception as e:
            from utils import get_logger
            logger = get_logger('delete_service')
            logger.warning(f'VACUUM 失败: {e}')

    def _cleanup_photo_files(self, album_name: str, year, filename: str, album_id: int = None, photo_id: int = None) -> None:
        """删除照片的物理文件与预览文件

        缩略图命名规则：{album_id}_{photo_id}.webp
        """
        file_path = DATA_DIR / album_name / str(year) / filename
        if file_path.exists():
            file_path.unlink()

        if album_id is not None and photo_id is not None:
            for ext in ['.webp', '.jpg']:
                preview_path = PREVIEW_DIR / f"{album_id}_{photo_id}{ext}"
                if preview_path.exists():
                    preview_path.unlink()

    def _parse_path_key(self, path_key: str) -> Optional[Dict[str, Any]]:
        """解析照片路径键，返回照片信息（使用索引查询）"""
        parts = path_key.split('/')
        if len(parts) != 3:
            return None

        album_name, year, filename = parts
        album = get_album_by_name(album_name)

        if not album:
            return None

        from db import get_photo_by_path
        return get_photo_by_path(album['id'], year, filename)

    def _cleanup_empty_year(self, album_id: int, year: int) -> None:
        """删除照片后检查该年份是否还有照片，若为空则清理年份数据和文件夹"""
        remaining_photos = get_photos_by_album(album_id, year)
        if len(remaining_photos) > 0:
            return

        album = get_album_by_id(album_id)
        album_name = album['name'] if album else None

        if album_name:
            year_dir = DATA_DIR / album_name / str(year)
            if year_dir.exists() and year_dir.is_dir():
                try:
                    if not any(year_dir.iterdir()):
                        year_dir.rmdir()
                except Exception:
                    pass

    @staticmethod
    def _cleanup_empty_album(album_id: int) -> None:
        """删除照片后检查相册是否为空，若为空则自动删除相册"""
        if count_photos_by_album(album_id) > 0:
            return

        from services.album_service import AlbumService
        album_service = AlbumService()
        try:
            album_service.delete_album(str(album_id))
        except ValueError:
            pass

    def _collect_photos_for_batch_delete(self, path_keys: List[str]) -> Dict[str, Any]:
        """收集待删除照片的元数据（photo_id/album/year/filename）

        复用单一连接执行所有查询，避免每张照片新建连接的开销。
        """
        photo_ids = []
        deleted_path_keys = []
        files_to_delete = []
        affected_album_ids = set()
        affected_years = {}
        album_cache: Dict[str, Any] = {}

        conn = get_db_connection()
        try:
            for path_key in path_keys:
                parsed = self._parse_path_key_into_parts(path_key, conn, album_cache)
                if not parsed:
                    continue

                album_id, album_name, year, filename, photo_id = parsed
                photo_ids.append(photo_id)
                deleted_path_keys.append(path_key)
                affected_album_ids.add(album_id)
                affected_years.setdefault(album_id, set()).add(int(year))
                files_to_delete.append((album_id, album_name, year, filename, photo_id))
        finally:
            conn.close()

        return {
            'photo_ids': photo_ids,
            'deleted_path_keys': deleted_path_keys,
            'files_to_delete': files_to_delete,
            'affected_album_ids': affected_album_ids,
            'affected_years': affected_years,
        }

    @staticmethod
    def _parse_path_key_into_parts(path_key: str, conn, album_cache: Dict[str, Any]):
        """解析单个 path_key 为 (album_id, album_name, year, filename, photo_id)，失败返回 None

        通过 db 层封装的 get_album_by_name / get_photo_by_path 查询，
        不在 service 层写裸 SQL。conn 由调用方管理生命周期。
        """
        parts = path_key.split('/')
        if len(parts) != 3:
            return None
        album_name, year, filename = parts

        if album_name not in album_cache:
            album = get_album_by_name(album_name, conn=conn)
            album_cache[album_name] = album['id'] if album else None
        album_id = album_cache[album_name]
        if not album_id:
            return None

        photo = get_photo_by_path(album_id, year, filename, conn=conn)
        if not photo:
            return None

        return (album_id, album_name, year, filename, photo['id'])

    @staticmethod
    def _batch_delete_db_records(photo_ids: List[int]) -> None:
        """单事务批量删除 DB 记录（分批避免 SQLite 参数上限）"""
        batch_delete_photos(photo_ids)

    @staticmethod
    def _batch_delete_files(files_to_delete: List[tuple]) -> None:
        """批量删除物理照片与预览文件（FS 失败不影响 DB 一致性）

        缩略图命名规则：{album_id}_{photo_id}.webp
        """
        for album_id, album_name, year, filename, photo_id in files_to_delete:
            file_path = DATA_DIR / album_name / year / filename
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass

            for ext in ['.webp', '.jpg']:
                preview_path = PREVIEW_DIR / f"{album_id}_{photo_id}{ext}"
                try:
                    if preview_path.exists():
                        preview_path.unlink()
                except Exception:
                    pass
