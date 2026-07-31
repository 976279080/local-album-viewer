#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP请求处理器模块 - 封装HTTP请求处理逻辑
遵循单一职责原则：仅负责HTTP协议处理，调用服务层处理业务逻辑

实际的路由方法实现分布在 routers/ 子包中的各 Mixin，
PhotoHandler 通过多继承组合获得所有路由方法。
"""

import json
import gzip
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any, Tuple

from config import DATA_DIR, PREVIEW_DIR, WEB_DIR, IMAGES_DIR
from services.album_service import AlbumService
from services.photo_service import PhotoService
from routers import (
    StaticRouterMixin,
    PhotoRouterMixin,
    AlbumRouterMixin,
    UploadRouterMixin,
    CommentRouterMixin,
    VersionRouterMixin,
    LicenseRouterMixin,
    check_auth as check_auth_request,
)


class PhotoHandler(
    BaseHTTPRequestHandler,
    StaticRouterMixin,
    PhotoRouterMixin,
    AlbumRouterMixin,
    UploadRouterMixin,
    CommentRouterMixin,
    VersionRouterMixin,
    LicenseRouterMixin,
):
    """HTTP 请求处理器 - 通过 Mixin 组合获得所有路由方法"""

    protocol_version = 'HTTP/1.1'

    def __init__(self, *args, **kwargs):
        self.album_service = AlbumService()
        self.photo_service = PhotoService()
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """禁用默认日志"""
        pass

    def send_json(self, data: Any, status: int = 200) -> None:
        """发送 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')

        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if hasattr(self, '_send_body') and self._send_body is False:
            return
        self.wfile.write(body)

    def send_error_json(self, msg: str, status: int = 400) -> None:
        """发送错误响应"""
        self.send_json({'error': msg}, status)

    def check_auth(self) -> bool:
        """检查密码认证（委托给 routers.auth_middleware.check_auth）"""
        if not check_auth_request(self.headers):
            self.send_error_json('密码错误', 401)
            return False
        return True

    def parse_path(self) -> Tuple[str, Dict[str, Any]]:
        """解析请求路径"""
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query, encoding='utf-8', keep_blank_values=True)

    def parse_request_body(self) -> Dict[str, Any]:
        """解析请求体JSON"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            raise ValueError("Invalid request body")

    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Auth')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self) -> None:
        """处理 GET 请求"""
        self._handle_image_request(self.path, True)

    def do_HEAD(self) -> None:
        """处理 HEAD 请求（检查文件存在性）"""
        self._handle_image_request(self.path, False)

    def _handle_image_request(self, path: str, send_body: bool) -> None:
        """处理图片请求（GET/HEAD）"""
        parsed = urllib.parse.urlparse(path)
        req_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query, encoding='utf-8', keep_blank_values=True)

        if req_path.startswith('/data/'):
            self._serve_static_file(req_path[6:], DATA_DIR, send_body)
            return

        if req_path.startswith('/previews/'):
            self._serve_static_file(req_path[10:], PREVIEW_DIR, send_body)
            return

        if req_path.startswith('/images/'):
            self._serve_static_file(req_path[8:], IMAGES_DIR, send_body)
            return

        if req_path.endswith('.js') and req_path not in self._routes['GET']:
            self.serve_file(WEB_DIR / req_path[1:], 'application/javascript')
            return

        handler_name = self._routes['GET'].get(req_path)
        if handler_name:
            handler = getattr(self, handler_name)
            handler(query)
        else:
            self.send_error_json('Not Found', 404)

    def do_POST(self) -> None:
        """处理 POST 请求"""
        path, _ = self.parse_path()

        handler_name = self._routes['POST'].get(path)
        if handler_name:
            handler = getattr(self, handler_name)
            handler()
        else:
            self.send_error_json('Not Found', 404)

    def do_DELETE(self) -> None:
        """处理 DELETE 请求"""
        path, _ = self.parse_path()

        handler_name = self._routes['DELETE'].get(path)
        if handler_name:
            handler = getattr(self, handler_name)
            handler()
        else:
            self.send_error_json('Not Found', 404)