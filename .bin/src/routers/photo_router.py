#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片查询路由 Mixin"""

from typing import Dict, Any
from db import get_summary


class PhotoRouterMixin:
    """照片相关只读 API 路由：summary / photos / photo / album-years / album-init / home-init"""

    def handle_summary(self, query: Dict[str, Any]) -> None:
        """返回相册和标签概览（直接查询数据库）"""
        summary = get_summary()
        self.send_json(summary)

    def handle_photos(self, query: Dict[str, Any]) -> None:
        """返回照片列表"""
        filters = {
            'album': query.get('album', [None])[0],
            'year': query.get('year', [None])[0],
            'type': query.get('type', ['all'])[0],
            'rating': query.get('rating', [None])[0],
            'tag': query.get('tag', [None])[0],
            'sort': query.get('sort', ['capture_time'])[0],
            'order': query.get('order', ['desc'])[0],
            'page': query.get('page', ['1'])[0],
            'page_size': query.get('page_size', ['200'])[0]
        }

        result = self.photo_service.get_photos(filters)
        self.send_json(result)

    def handle_photo_detail(self, query: Dict[str, Any]) -> None:
        """返回单张照片详情（含标签和评论）"""
        photo_id = query.get('id', [None])[0]
        if not photo_id:
            self.send_error_json('Missing photo_id', 400)
            return

        try:
            photo_id_int = int(photo_id)
        except ValueError:
            self.send_error_json('Invalid photo_id', 400)
            return

        try:
            result = self.photo_service.get_photo_detail(photo_id_int)
            self.send_json(result)
        except ValueError as e:
            msg = str(e)
            if '不存在' in msg:
                self.send_error_json(msg, 404)
            else:
                self.send_error_json(msg, 400)
        except Exception as e:
            self.send_error_json(f'Error: {e}', 500)

    def handle_album_years(self, query: Dict[str, Any]) -> None:
        """返回相册的年份列表及各年份照片数"""
        album_id = query.get('album', [None])[0]
        if not album_id:
            self.send_error_json('缺少album参数')
            return

        try:
            result = self.photo_service.get_album_years(album_id)
            self.send_json(result)
        except ValueError as e:
            self.send_error_json(str(e))

    def _build_album_init_data(self, album_id: str, year_param: str = None) -> Dict[str, Any]:
        """构建相册初始化数据（album-years + photos）"""
        year_data = self.photo_service.get_album_years(album_id)

        total = year_data.get('total', 0)
        years = year_data.get('years', [])

        filters = {'album': album_id, 'page_size': 100000}

        if total > 2000:
            year_data['use_year_mode'] = True
            if year_param is not None and year_param == '':
                year_data['selected_year'] = ''
            elif year_param and years:
                if any(str(y['year']) == str(year_param) for y in years):
                    filters['year'] = str(year_param)
                    year_data['selected_year'] = str(year_param)
                else:
                    latest = str(years[0]['year']) if years else ''
                    filters['year'] = latest
                    year_data['selected_year'] = latest
            elif years:
                latest = str(years[0]['year'])
                filters['year'] = latest
                year_data['selected_year'] = latest
            else:
                year_data['selected_year'] = ''
        else:
            year_data['use_year_mode'] = False
            year_data['selected_year'] = ''

        photos_data = self.photo_service.get_photos(filters)
        return {'album_years': year_data, 'photos': photos_data}

    def handle_album_init(self, query: Dict[str, Any]) -> None:
        """相册初始化：一次返回 album-years + photos"""
        album_id = query.get('album', [None])[0]
        if not album_id:
            self.send_error_json('缺少album参数')
            return

        try:
            year_param = query.get('year', [None])[0]
            data = self._build_album_init_data(album_id, year_param)
            data['status'] = 'ok'
            self.send_json(data)
        except ValueError as e:
            self.send_error_json(str(e))

    def handle_home_init(self, query: Dict[str, Any]) -> None:
        """首页初始化：一次返回 summary + album-years + photos"""
        summary_data = get_summary()

        album_id = query.get('album', [None])[0]
        if not album_id and summary_data.get('members'):
            album_id = list(summary_data['members'].keys())[0]

        album_data = None
        if album_id:
            try:
                album_data = self._build_album_init_data(album_id)
            except ValueError as e:
                self.send_error_json(str(e))
                return

        result = {'status': 'ok', 'summary': summary_data}
        if album_data:
            result.update(album_data)
        self.send_json(result)