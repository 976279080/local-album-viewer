#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片更新服务 - 封装照片更新相关业务逻辑
遵循单一职责原则：仅负责照片元数据更新
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Callable

from config import DATA_DIR, PREVIEW_DIR
from constants import MAX_TITLE_LENGTH, MAX_COMMENT_LENGTH, MAX_EDIT_COUNT
from utils import validate_title_chars, parse_iso_to_timestamp, load_password
from db import (
    get_photo_by_id, update_photo as db_update_photo,
    get_album_by_id, update_photo_create_time,
    add_tags_to_photo, remove_tags_from_photo, get_photo_tags, get_tag_by_name,
    get_tag_by_id, create_tag,
    add_comment, delete_comment, delete_all_comments, get_photo_comments,
    batch_add_comments,
    get_db_connection,
)
from services._tag_helpers import ensure_tag_definition


class PhotoUpdateService:
    """照片更新服务类"""

    def __init__(self, query_service=None):
        self._query_service = query_service

    def update_photo(self, path_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新照片元数据

        事务顺序：先开事务执行 SQL，再执行文件操作，文件成功则提交事务，失败则回滚。
        确保数据库与文件系统的数据一致性。
        """
        photo = self._parse_path_key(path_key)
        if not photo:
            raise ValueError("照片不存在")

        photo_id = photo['id']

        if self._is_update_unchanged(photo_id, photo, data):
            updated_photo = get_photo_by_id(photo_id)
            meta = self._get_updated_photo_meta(updated_photo, path_key)
            meta['no_change'] = True
            return meta

        conn = None
        file_operations: List[Callable[[], None]] = []
        try:
            conn = get_db_connection()
            conn.execute('BEGIN IMMEDIATE')

            update_fields = {}

            self._handle_create_time_update(photo_id, photo, data, conn, file_operations)
            self._handle_title_update(photo_id, photo, data, update_fields, conn, file_operations)
            self._handle_rating_update(data, update_fields)
            self._handle_tags_update(photo_id, data, conn)
            self._handle_comments_update(photo_id, data, conn)

            if update_fields:
                db_update_photo(photo_id, conn=conn, **update_fields)

            for op in file_operations:
                op()

            conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise e
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        updated_photo = get_photo_by_id(photo_id)
        return self._get_updated_photo_meta(updated_photo, path_key)

    def _handle_create_time_update(self, photo_id: int, photo: Dict[str, Any],
                                    data: Dict[str, Any],
                                    conn, file_operations: List[Callable[[], None]]) -> None:
        """处理拍摄时间更新（含跨年移动文件）"""
        new_create_time = data.get('create_time')
        if not new_create_time:
            return

        self._update_create_time(photo_id, photo, new_create_time, data.get('password', ''), conn, file_operations)
        updated_photo = get_photo_by_id(photo_id, conn=conn)
        if updated_photo:
            photo['year'] = updated_photo.get('year', photo['year'])
            photo['filename'] = updated_photo.get('filename', photo['filename'])
            photo['create_time'] = updated_photo.get('create_time', photo['create_time'])

    def _handle_title_update(self, photo_id: int, photo: Dict[str, Any],
                              data: Dict[str, Any],
                              update_fields: Dict[str, Any],
                              conn, file_operations: List[Callable[[], None]]) -> None:
        """处理标题更新（可能触发文件名重命名）"""
        if 'title' not in data:
            return

        new_title = data['title'][:MAX_TITLE_LENGTH]
        validate_title_chars(new_title)
        update_fields['title'] = new_title

        old_title = photo.get('title', '')
        if old_title != new_title:
            self._update_photo_filename(photo_id, photo, new_title, conn, file_operations)
            updated_photo = get_photo_by_id(photo_id, conn=conn)
            if updated_photo:
                photo['filename'] = updated_photo.get('filename', photo['filename'])

    @staticmethod
    def _handle_rating_update(data: Dict[str, Any], update_fields: Dict[str, Any]) -> None:
        """处理评分更新"""
        if 'rating' in data:
            update_fields['rating'] = int(data['rating'])

    def _handle_tags_update(self, photo_id: int, data: Dict[str, Any], conn) -> None:
        """处理标签批量更新"""
        if 'tags' in data:
            self._update_photo_tags(photo_id, data['tags'], conn)

    def _handle_comments_update(self, photo_id: int, data: Dict[str, Any], conn) -> None:
        """处理评论相关更新（三种模式：批量替换/新增单条/删除单条）"""
        if 'comments' in data:
            self._update_photo_comments(photo_id, data['comments'], conn)
            return

        if 'add_comment' in data:
            add_comment(photo_id, data['add_comment'][:MAX_COMMENT_LENGTH], conn=conn)
            return

        if 'delete_comment' in data:
            self._delete_comment_by_index(photo_id, data['delete_comment'], conn)

    def _is_update_unchanged(self, photo_id: int, photo: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """判断提交内容是否与照片当前状态完全一致"""
        keys_to_check = {'title', 'rating', 'tags'}
        submitted_keys = keys_to_check & set(data.keys())
        if not submitted_keys:
            return False

        if set(data.keys()) - keys_to_check - {'path_key', 'password'}:
            return False

        if 'title' in data:
            new_title = (data['title'] or '')[:MAX_TITLE_LENGTH]
            old_title = photo.get('title', '') or ''
            if new_title != old_title:
                return False

        if 'rating' in data:
            try:
                new_rating = int(data['rating'])
            except (TypeError, ValueError):
                return False
            old_rating = int(photo.get('rating', 0) or 0)
            if new_rating != old_rating:
                return False

        if 'tags' in data:
            new_tags = data['tags'] or []
            if not isinstance(new_tags, list):
                return False
            existing_tags = get_photo_tags(photo_id)
            existing_tag_names = [t['name'] for t in existing_tags]
            if set(new_tags) != set(existing_tag_names):
                return False

        return True

    def _update_create_time(self, photo_id: int, photo: Dict[str, Any],
                            create_time_str: str,
                            password: str = '', conn=None,
                            file_operations: List[Callable[[], None]] = None) -> None:
        """更新照片拍摄时间（最多修改两次）"""
        if password != load_password():
            raise ValueError("密码错误")

        edit_count = photo.get('edit_count', 0)
        if edit_count >= MAX_EDIT_COUNT:
            raise ValueError("该照片拍摄时间已修改过两次，无法再次修改")

        new_time = self._parse_create_time_str(create_time_str)
        new_year = new_time.year
        new_time_ts = int(new_time.timestamp())

        album = get_album_by_id(photo['album_id'], conn=conn)
        album_name = album['name'] if album else str(photo['album_id'])

        if new_year != photo['year']:
            if file_operations is not None:
                file_operations.append(
                    lambda: self._move_photo_files_to_new_year(
                        photo['album_id'], photo_id, album_name,
                        photo['year'], new_year, photo['filename']
                    )
                )
            else:
                self._move_photo_files_to_new_year(photo['album_id'], photo_id, album_name, photo['year'], new_year, photo['filename'])

        self._update_create_time_in_db(photo_id, new_time_ts, new_year, edit_count, conn)

    @staticmethod
    def _parse_create_time_str(create_time_str: str) -> datetime:
        """解析时间字符串，支持 ISO 与 'YYYY-MM-DD HH:MM:SS' 两种格式"""
        try:
            return datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))
        except Exception:
            try:
                return datetime.strptime(create_time_str, '%Y-%m-%d %H:%M:%S')
            except Exception:
                raise ValueError("时间格式错误")

    @staticmethod
    def _move_photo_files_to_new_year(album_id: int, photo_id: int, album_name: str, old_year: int,
                                       new_year: int, filename: str) -> None:
        """跨年移动照片文件（缩略图用album_id_photo_id命名，无需移动）"""
        new_album_dir = DATA_DIR / album_name / str(new_year)
        new_album_dir.mkdir(parents=True, exist_ok=True)

        old_file_path = DATA_DIR / album_name / str(old_year) / filename
        new_file_path = DATA_DIR / album_name / str(new_year) / filename
        old_file_path.rename(new_file_path)

        old_year_dir = DATA_DIR / album_name / str(old_year)
        if old_year_dir.exists() and old_year_dir.is_dir():
            try:
                if not any(old_year_dir.iterdir()):
                    old_year_dir.rmdir()
            except Exception:
                pass

    @staticmethod
    def _update_create_time_in_db(photo_id: int, new_time_ts: int,
                                   new_year: int, edit_count: int, conn=None) -> None:
        """更新数据库中的拍摄时间记录"""
        update_photo_create_time(photo_id, new_time_ts, new_year, edit_count, conn=conn)

    def _update_photo_filename(self, photo_id: int, photo: Dict[str, Any], new_title: str,
                                conn=None,
                                file_operations: List[Callable[[], None]] = None) -> None:
        """更新照片文件名（格式：id.ext 或 id_title.ext）

        数据库更新在事务中执行，文件操作推迟到事务提交前执行。
        """
        old_filename = photo['filename']
        ext = Path(old_filename).suffix

        if new_title:
            new_filename = f"{photo_id}_{new_title}{ext}"
        else:
            new_filename = f"{photo_id}{ext}"

        if old_filename == new_filename:
            return

        album = get_album_by_id(photo['album_id'], conn=conn)
        album_name = album['name'] if album else str(photo['album_id'])
        year = photo['year']

        old_file_path = DATA_DIR / album_name / str(year) / old_filename
        new_file_path = DATA_DIR / album_name / str(year) / new_filename

        if file_operations is not None:
            def _rename_file():
                if old_file_path.exists():
                    old_file_path.rename(new_file_path)
            file_operations.append(_rename_file)
        else:
            if old_file_path.exists():
                old_file_path.rename(new_file_path)

        db_update_photo(photo_id, filename=new_filename, conn=conn)

    def _update_photo_comments(self, photo_id: int, comments: List[Dict[str, Any]], conn) -> None:
        """更新照片评论（全量替换，批量插入）"""
        delete_all_comments(photo_id, conn=conn)
        texts = [comment.get('text', '') for comment in comments if comment.get('text', '').strip()]
        if texts:
            batch_add_comments(photo_id, texts, conn=conn)

    def _update_photo_tags(self, photo_id: int, tags: List[str], conn) -> None:
        """更新照片标签（批量确保标签定义，避免循环查询）"""
        tag_list = [t[:MAX_TITLE_LENGTH] for t in tags]
        remove_tags_from_photo(photo_id, conn=conn)
        if tag_list:
            add_tags_to_photo(photo_id, tag_list, conn=conn)

        if tag_list:
            self._ensure_tag_definitions_batch(tag_list, conn)

        from db.tag_repository import cleanup_unused_tags
        cleanup_unused_tags(conn=conn)

    def _ensure_tag_definitions_batch(self, tag_names: List[str], conn) -> None:
        """批量确保标签定义存在（复用外部事务连接，避免死锁）"""
        tag_names = [t.strip() for t in tag_names if t.strip()]
        if not tag_names:
            return

        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(tag_names))
        cursor.execute(f'SELECT name, color FROM tags WHERE name IN ({placeholders})', tag_names)
        existing_tags = {row['name']: row['color'] for row in cursor.fetchall()}

        missing_tags = [name for name in tag_names if name not in existing_tags]
        for t in missing_tags:
            tag_id = create_tag(t, conn=conn)
            tag = get_tag_by_id(tag_id, conn=conn)
            if tag:
                existing_tags[t] = tag['color']

    def _delete_comment_by_index(self, photo_id: int, index_str: str, conn) -> None:
        """按索引删除评论"""
        try:
            idx = int(index_str)
            comments = get_photo_comments(photo_id, conn=conn)
            if 0 <= idx < len(comments):
                delete_comment(comments[idx]['id'], conn=conn)
        except Exception:
            pass

    def _get_updated_photo_meta(self, photo: Dict[str, Any], path_key: str) -> Dict[str, Any]:
        """获取更新后的照片元数据"""
        photo_id = photo['id']
        updated_photo = get_photo_by_id(photo_id)
        if not updated_photo:
            updated_photo = photo

        album_name = updated_photo.get('album_name')
        if not album_name:
            album = get_album_by_id(updated_photo['album_id'])
            album_name = album['name'] if album else str(updated_photo['album_id'])

        tags = get_photo_tags(photo_id)
        tag_names = [t['name'] for t in tags]
        comments = get_photo_comments(photo_id)

        new_year = updated_photo.get('year', photo.get('year'))
        year_str = str(new_year)
        filename = updated_photo.get('filename', photo.get('filename', ''))

        file_path = DATA_DIR / album_name / year_str / filename
        preview_url = f'/previews/{updated_photo["album_id"]}_{photo_id}.webp'
        original_url = f'/data/{album_name}/{year_str}/{filename}'
        new_path_key = f"{album_name}/{year_str}/{filename}"

        return {
            'id': photo_id,
            'album_id': updated_photo['album_id'],
            'year': new_year,
            'filename': filename,
            'path_key': new_path_key,
            'absolute_path': str(file_path),
            'preview_url': preview_url,
            'original_url': original_url,
            'title': updated_photo.get('title', ''),
            'rating': updated_photo.get('rating', 0),
            'edit_count': updated_photo.get('edit_count', 0),
            'tags': tag_names,
            'comments': comments,
            'comment_count': len(comments),
            'size': photo.get('size', 0),
            'width': photo.get('width'),
            'height': photo.get('height'),
            'create_time': updated_photo.get('create_time', photo.get('create_time')) if updated_photo else photo.get('create_time'),
            'update_time': updated_photo.get('update_time', photo.get('update_time')) if updated_photo else photo.get('update_time')
        }

    def _parse_path_key(self, path_key: str):
        """解析路径键获取照片（通过 delete service 或自行实现）"""
        from services.photo_delete_service import PhotoDeleteService
        delete_service = PhotoDeleteService()
        return delete_service._parse_path_key(path_key)
