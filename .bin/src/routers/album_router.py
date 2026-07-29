#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""相册管理路由 Mixin"""


class AlbumRouterMixin:
    """相册管理 API 路由：create / rename / delete"""

    def handle_create_album(self) -> None:
        """创建新相册"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            name = str(data.get('name', '')).strip()

            album_id = self.album_service.create_album(name)
            self.send_json({'status': 'ok', 'album_id': album_id, 'name': name})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            self.send_error_json(f'创建失败: {str(e)}')

    def handle_rename_album(self) -> None:
        """重命名相册"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            album_id = str(data.get('album_id', '')).strip()
            new_name = str(data.get('name', '')).strip()

            if not album_id:
                self.send_error_json('缺少album_id参数')
                return
            if not new_name:
                self.send_error_json('相册名称不能为空')
                return

            album_info = self.album_service.get_album_info(album_id)
            if album_info and album_info['name'] == new_name:
                self.send_json({'status': 'ok', 'album_id': album_id, 'name': new_name})
                return

            self.album_service.rename_album(album_id, new_name)

            self.send_json({'status': 'ok', 'album_id': album_id, 'name': new_name})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            self.send_error_json(f'重命名失败: {str(e)}')

    def handle_delete_album(self) -> None:
        """删除相册"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            album_id = str(data.get('album_id', '')).strip()

            self.album_service.delete_album(album_id)
            self.send_json({'status': 'ok'})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            self.send_error_json(f'删除相册失败: {str(e)}')
