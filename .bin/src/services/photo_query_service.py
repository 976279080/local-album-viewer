#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片查询服务 - 封装照片查询相关业务逻辑
遵循单一职责原则：仅负责照片查询与数据组装
"""

from typing import Dict, Any, List, Optional
from pathlib import Path

from config import DATA_DIR, PREVIEW_DIR
from constants import DEFAULT_PAGE_SIZE, DEFAULT_COLOR
from db import (
    get_all_photos_with_pagination, get_photo_with_album,
    get_photo_tags_with_color, get_photo_tags, batch_get_photo_tags,
    get_album_by_id, get_photo_count, get_photo_by_id,
    get_summary,
)


class PhotoQueryService:
    """照片查询服务类"""

    def get_photo_count(self, album_id: Optional[str] = None) -> Dict[str, Any]:
        """获取照片数量统计"""
        if album_id:
            db_album_id = self._resolve_album_id(album_id)
            if db_album_id:
                return get_photo_count(db_album_id)
        return get_photo_count(None)

    def get_album_years(self, album_id: str) -> Dict[str, Any]:
        """获取相册的年份列表及各年份照片数（直接查数据库）"""
        db_album_id = self._resolve_album_id(album_id)
        if not db_album_id:
            raise ValueError(f'相册不存在: {album_id}')

        album = get_album_by_id(db_album_id)
        album_name = album['name'] if album else str(db_album_id)

        counts = get_photo_count(db_album_id)
        by_year = counts.get('by_year', {})
        total = counts.get('total', 0)

        years = [
            {'year': year, 'count': cnt}
            for year, cnt in sorted(by_year.items(), key=lambda x: str(x[0]), reverse=True)
        ]

        return {
            'status': 'ok',
            'album_id': str(db_album_id),
            'album_name': album_name,
            'total': total,
            'years': years
        }

    def get_photos(self, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取照片列表（支持筛选和分页）

        列表场景使用精简字段（compact=True），移除详情页才需要的
        absolute_path/size/width/height/filename/upload_time/album_color/
        album_name/edit_count 等字段，大幅减小响应体积。
        详情页通过 get_photo_detail 获取完整字段。
        """
        if filters is None:
            filters = {}

        db_filters = self._build_db_filters(filters)

        photo_type = filters.get('type', 'all')
        sort_by = filters.get('sort', 'capture_time')
        sort_order = filters.get('order', 'desc')
        page = int(filters.get('page', 1))
        page_size = int(filters.get('page_size', DEFAULT_PAGE_SIZE))

        result = get_all_photos_with_pagination(
            db_filters, page, page_size,
            sort_by=sort_by, sort_order=sort_order,
            photo_type=photo_type
        )
        photos = result['photos']

        photo_tags = self._batch_get_photo_tags([p['id'] for p in photos])

        photo_list = [
            self._build_photo_data(photo, photo_tags.get(photo['id'], []), compact=True)
            for photo in photos
        ]

        return {
            'photos': photo_list,
            'total': result['total'],
            'page': page,
            'page_size': page_size
        }

    def get_photo_detail(self, photo_id: int) -> Dict[str, Any]:
        """获取单张照片详情（含标签和评论）"""
        photo = get_photo_with_album(photo_id)
        if not photo:
            raise ValueError('照片不存在')

        photo = dict(photo)
        tag_names = get_photo_tags_with_color(photo_id)
        from db import get_photo_comments
        comments = get_photo_comments(photo_id)

        photo_data = self._build_photo_data(photo, [t['name'] for t in tag_names])
        photo_data['comments'] = comments

        return {
            'status': 'ok',
            'photo': photo_data
        }

    def build_photo_data(self, photo: Dict[str, Any], tag_names: List[str] = None) -> Dict[str, Any]:
        """构建照片数据字典（公开方法供其他服务使用）"""
        return self._build_photo_data(photo, tag_names)

    @staticmethod
    def _resolve_album_id(album_id: str) -> Optional[int]:
        """解析相册ID，支持数字ID和name"""
        try:
            return int(album_id)
        except ValueError:
            from db import get_album_by_name
            album = get_album_by_name(album_id)
            return album['id'] if album else None

    @staticmethod
    def _batch_get_photo_tags(photo_ids: List[int]) -> Dict[int, List[str]]:
        """批量获取照片的标签（单次查询，避免 N+1）"""
        return batch_get_photo_tags(photo_ids)

    def _build_db_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """构建数据库筛选条件"""
        db_filters = {}

        album_filter = filters.get('album')
        if album_filter:
            db_album_id = self._resolve_album_id(album_filter)
            if db_album_id:
                db_filters['album_id'] = db_album_id

        year_filter = filters.get('year')
        if year_filter:
            db_filters['year'] = year_filter

        rating_filter = filters.get('rating')
        if rating_filter:
            db_filters['rating'] = rating_filter

        tag_filter = filters.get('tag')
        if tag_filter:
            db_filters['tag'] = tag_filter

        return db_filters

    def _build_photo_data(self, photo: Dict[str, Any], tag_names: List[str] = None, compact: bool = False) -> Dict[str, Any]:
        """构建照片数据字典

        compact=True 时仅返回列表渲染必需的字段，移除详情页才用的
        absolute_path/size/width/height/filename/upload_time/album_color/
        album_name/edit_count，详情页通过 get_photo_detail 补全。
        """
        filename = photo['filename']
        album_name = photo.get('album_name', str(photo['album_id']))
        year = str(photo['year'])

        if tag_names is None:
            tag_names = self._get_photo_tag_names(photo)

        paths = self._build_photo_paths(photo['album_id'], photo['id'], album_name, year, filename)

        # 列表渲染必需字段（含详情页打开瞬间需要的 original_url）
        photo_data = {
            'id': photo['id'],
            'album_id': photo['album_id'],
            'year': photo['year'],
            'path_key': f"{album_name}/{year}/{filename}",
            'preview_url': paths['preview_url'],
            'original_url': paths['original_url'],
            'title': photo.get('title', ''),
            'rating': photo.get('rating', 0),
            'comment_count': photo.get('comment_count', 0),
            'tags': tag_names,
            'file_type': photo.get('file_type', 'image'),
            'create_time': photo.get('create_time'),
            'update_time': photo.get('update_time')
        }

        # 详情页完整字段
        if not compact:
            photo_data.update({
                'album_name': album_name,
                'album_color': photo.get('album_color', DEFAULT_COLOR),
                'filename': filename,
                'absolute_path': paths['absolute_path'],
                'edit_count': photo.get('edit_count', 0),
                'size': self._resolve_photo_size(photo, paths['absolute_path']),
                'width': photo.get('width'),
                'height': photo.get('height'),
                'upload_time': photo.get('upload_time')
            })

        return photo_data

    @staticmethod
    def _build_photo_paths(album_id: int, photo_id: int, album_name: str, year: str, filename: str) -> Dict[str, str]:
        """构建照片的所有路径字符串"""
        file_path = DATA_DIR / album_name / year / filename
        # URL 路径段需进行百分号编码，避免中文/特殊字符导致浏览器或代理解析异常
        from urllib.parse import quote
        encoded_segments = '/'.join(quote(part, safe='') for part in (album_name, year, filename))
        return {
            'absolute_path': str(file_path),
            'preview_url': f'/previews/{album_id}_{photo_id}.webp',
            'original_url': f'/data/{encoded_segments}',
        }

    @staticmethod
    def _get_photo_tag_names(photo: Dict[str, Any]) -> List[str]:
        """获取照片标签名称列表（DB 兜底查询）"""
        tag_count = photo.get('tag_count', 0)
        if tag_count <= 0:
            return []
        tags = get_photo_tags(photo['id'])
        return [t['name'] for t in tags]

    @staticmethod
    def _resolve_photo_size(photo: Dict[str, Any], absolute_path: str) -> int:
        """解析照片大小（列表场景直接返回 DB 值，避免 N 次文件系统 stat）
        
        历史数据中 size=0 的照片，在详情页或迁移脚本中统一回填，
        列表查询不做文件系统 IO 兜底，否则 200 张照片可能触发 200 次磁盘 stat。
        """
        return photo.get('size', 0)
