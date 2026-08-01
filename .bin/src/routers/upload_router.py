#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上传与照片写操作路由 Mixin"""

import json
import traceback
from typing import Dict, Any

from utils import parse_multipart, get_logger

_logger = get_logger('upload_router')


class UploadRouterMixin:
    """照片写入 API 路由：upload / delete / batch-* / update"""

    def handle_upload(self) -> None:
        """处理上传"""
        if not self.check_auth():
            return

        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_error_json('Invalid content type')
            return

        boundary = None
        for part in content_type.split(';'):
            if part.strip().startswith('boundary='):
                boundary = part.strip()[len('boundary='):].strip('"')
                break

        if not boundary:
            self.send_error_json('Missing boundary')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_length)

        form = parse_multipart(data, boundary)

        # 兼容两种字段名：电脑端(album/new_album) / 移动端(album_name/new_album_name)
        album_name = (form.get('album') or form.get('album_name') or '').strip()
        new_album = (form.get('new_album') or form.get('new_album_name') or '').strip()
        tags_str = form.get('tags', '[]')

        # tags 支持两种格式：JSON 数组（电脑端）或 逗号/空格分隔字符串（移动端）
        tags = []
        try:
            tags = json.loads(tags_str)
            if not isinstance(tags, list): tags = []
        except Exception:
            if tags_str:
                import re
                tags = [t for t in re.split(r'[,，\s]+', tags_str) if t]

        file_items = []
        if isinstance(form.get('file'), list):
            file_items = form.get('file')
        elif 'file' in form:
            file_items = [form['file']]

        create_time_str = form.get('create_time', '')
        width = form.get('width', '')
        height = form.get('height', '')
        original_name = form.get('original_name', '')
        file_size = form.get('size', '')
        thumbnail_item = form.get('thumbnail')

        try:
            uploaded = self.photo_service.upload_photos(
                album_name, new_album, tags, file_items,
                create_time_str, width, height, file_size,
                thumbnail_item
            )
            self.send_json({'uploaded': uploaded, 'count': len(uploaded)})
        except ValueError as e:
            self.send_error_json(str(e))

    def handle_delete(self) -> None:
        """删除单张照片"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            path_key = data.get('path_key', '')
        except Exception:
            self.send_error_json('Invalid request')
            return

        try:
            self.photo_service.delete_photo(path_key)
            self.send_json({'status': 'ok'})
        except ValueError as e:
            self.send_error_json(str(e))

    def handle_batch_delete(self) -> None:
        """批量删除"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            path_keys = data.get('path_keys', [])
        except Exception:
            self.send_error_json('Invalid request')
            return

        try:
            result = self.photo_service.batch_delete(path_keys)
            self.send_json({'status': 'ok', 'deleted_count': result.get('deleted_count', 0), 'deleted_path_keys': result.get('deleted_path_keys', [])})
        except Exception as e:
            self.send_error_json(f'批量删除失败: {str(e)}')

    def handle_batch_tag(self) -> None:
        """批量打标签"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            path_keys = data.get('path_keys', [])
            tags = data.get('tags', [])
        except Exception:
            self.send_error_json('Invalid request')
            return

        result = self.photo_service.batch_tag(path_keys, tags)
        self.send_json({'status': 'ok', 'updated': result.get('updated', []), 'updated_count': result.get('updated_count', 0)})

    def handle_batch_clear_tags(self) -> None:
        """批量清空标签"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            path_keys = data.get('path_keys', [])
        except Exception:
            self.send_error_json('Invalid request')
            return

        result = self.photo_service.batch_clear_tags(path_keys)
        self.send_json({'status': 'ok', 'updated': result.get('updated', []), 'updated_count': result.get('updated_count', 0)})

    def handle_update(self) -> None:
        """更新照片元数据"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            path_key = data.get('path_key', '')
        except Exception:
            self.send_error_json('Invalid request')
            return

        data['password'] = self.headers.get('X-Auth', '')

        try:
            meta = self.photo_service.update_photo(path_key, data)
            self.send_json({'status': 'ok', 'meta': meta})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            _logger.error(f"handle_update 异常 path_key={path_key}: {e}\n{traceback.format_exc()}")
            self.send_error_json(f'修改失败: {str(e)}')
