#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态资源路由 Mixin"""

import re
import shutil
from pathlib import Path
from typing import Dict, Any

from config import DATA_DIR, PREVIEW_DIR, WEB_DIR
from utils import get_logger

_logger = get_logger('static_router')


class StaticRouterMixin:
    """静态资源路由：HTML / CSS / JS / 媒体文件"""

    _routes = {
        'GET': {
            '/': 'serve_index',
            '/index.html': 'serve_index',
            '/upload.html': 'serve_upload',
            '/subscribe.html': 'serve_subscribe',
            '/generate_license.html': 'serve_generate_license',
            '/style.css': 'serve_style',
            '/app.js': 'serve_app_js',
            '/media-processor.js': 'serve_media_processor_js',
            '/vue.global.min.js': 'serve_vue_min',
            '/api/summary': 'handle_summary',
            '/api/photos': 'handle_photos',
            '/api/photo': 'handle_photo_detail',
            '/api/album-years': 'handle_album_years',
            '/api/album-init': 'handle_album_init',
            '/api/home-init': 'handle_home_init',
            '/api/comments': 'handle_comments',
            '/api/version/check': 'handle_version_check',
            '/api/version/list': 'handle_version_list',
            '/api/license/status': 'handle_license_status',
            '/api/license/config': 'handle_get_license_config',
        },
        'POST': {
            '/api/albums/create': 'handle_create_album',
            '/api/albums/rename': 'handle_rename_album',
            '/api/albums/delete': 'handle_delete_album',
            '/api/upload': 'handle_upload',
            '/api/delete': 'handle_delete',
            '/api/batch-delete': 'handle_batch_delete',
            '/api/batch-tag': 'handle_batch_tag',
            '/api/batch-clear-tags': 'handle_batch_clear_tags',
            '/api/update': 'handle_update',
            '/api/comments/add': 'handle_add_comment',
            '/api/comments/delete': 'handle_delete_comment',
            '/api/license/activate': 'handle_license_activate',
            '/api/license/clear': 'handle_license_clear',
            '/api/license/config': 'handle_set_license_config',
            '/api/verify': 'handle_verify',
        },
        'DELETE': {}
    }

    def serve_file(self, filepath: Path, content_type: str) -> None:
        """提供静态文件

        文件不存在返回 404，其他 IO/系统异常返回 500（避免把真实错误伪装成 404）。
        """
        try:
            content = filepath.read_bytes()
        except FileNotFoundError:
            self.send_error_json('File Not Found', 404)
            return
        except OSError as e:
            _logger.warning(f"读取静态文件失败 path={filepath}: {e}")
            self.send_error_json('Read error', 500)
            return

        try:
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8')
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            _logger.exception(f"响应静态文件失败 path={filepath}: {e}")
            self.send_error_json('Read error', 500)

    def _serve_static_file(self, rel_path: str, base_dir: Path, send_body: bool) -> None:
        """提供静态文件（data/previews目录），支持 Range 请求

        拆分为路径校验 / Content-Type 解析 / Range 解析 / Cache 策略 / 流式写入五个步骤。
        """
        import urllib.parse

        decoded_path = urllib.parse.unquote(rel_path)

        # 1. 路径校验（含越界检查）
        file_path = self._resolve_static_path(decoded_path, base_dir)
        if file_path is None:
            return  # 校验失败已发响应
        if not file_path.exists():
            self.send_error_json('File not found', 404)
            return

        content_type = self._resolve_content_type(file_path)

        try:
            file_size = file_path.stat().st_size
            range_header = self.headers.get('Range') or self.headers.get('range') if hasattr(self, 'headers') else None

            # 2. Range 头解析（决定走 200 还是 206）
            if range_header and range_header.startswith('bytes='):
                parsed = self._parse_byte_range(range_header, file_size)
                if parsed is None:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{file_size}')
                    self.end_headers()
                    return
                start, end = parsed
                content_length = end - start + 1

                self.send_response(206)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(content_length))
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Accept-Ranges', 'bytes')
            else:
                start, end = 0, file_size - 1
                content_length = file_size

                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(content_length))
                self.send_header('Accept-Ranges', 'bytes')

            # 3. Cache-Control 策略
            self.send_header('Cache-Control', self._get_static_cache_control(base_dir, decoded_path))
            self.end_headers()

            # 4. 流式写入响应体
            if send_body:
                self._stream_file(file_path, start, end)
        except FileNotFoundError:
            self.send_error_json('File not found', 404)
        except Exception as e:
            _logger.exception(f"读取文件失败 path={file_path}: {e}")
            self.send_error_json('Read error', 500)

    def _resolve_static_path(self, decoded_path: str, base_dir: Path):
        """校验并返回安全的静态文件路径；不合法时发响应并返回 None"""
        if '..' in decoded_path or decoded_path.startswith('/'):
            self.send_error_json('Invalid path', 403)
            return None
        file_path = base_dir / decoded_path
        try:
            file_path.resolve().relative_to(base_dir.resolve())
        except ValueError:
            self.send_error_json('Invalid path', 403)
            return None
        return file_path

    @staticmethod
    def _resolve_content_type(file_path: Path) -> str:
        """根据扩展名解析 Content-Type"""
        content_types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.webp': 'image/webp', '.bmp': 'image/bmp',
            '.mp4': 'video/mp4', '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
        }
        return content_types.get(file_path.suffix.lower(), 'application/octet-stream')

    @staticmethod
    def _parse_byte_range(range_header: str, file_size: int):
        """解析 Range 头，返回 (start, end) 或 None（无效范围，调用方应发 416）

        支持三种形式：
        - bytes=N-       → [N, file_size-1]
        - bytes=-N       → [file_size-N, file_size-1]（末尾 N 字节）
        - bytes=N-M      → [N, M]
        """
        range_str = range_header[6:].strip()  # 去掉 'bytes=' 前缀
        start, end = None, None

        if range_str.startswith('-'):
            suffix_length = int(range_str[1:])
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        elif '-' in range_str:
            parts = range_str.split('-', 1)
            start = int(parts[0]) if parts[0] else None
            end = int(parts[1]) if parts[1] else None

        if start is None:
            start = 0
        if end is None or end >= file_size:
            end = file_size - 1

        if start > end or start >= file_size:
            return None  # 无效范围

        return (start, end)

    @staticmethod
    def _get_static_cache_control(base_dir: Path, decoded_path: str) -> str:
        """根据目录和扩展名决定 Cache-Control 策略"""
        if base_dir == PREVIEW_DIR:
            return 'public, max-age=86400'
        if decoded_path.endswith('.css') or decoded_path.endswith('.js'):
            return 'no-cache, no-store, must-revalidate'
        return 'public, max-age=3600'

    def _stream_file(self, file_path: Path, start: int, end: int) -> None:
        """分块流式写入响应体"""
        chunk_size = 65536
        with open(file_path, 'rb') as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)

    def _serve_inlined_page(self, html_name: str, css_name: str, js_name: str, *, no_cache: bool = True) -> None:
        """提供内联 CSS/JS 的 HTML 页面（减少 HTTP 请求数）

        将 <link>/<script> 标签替换为内联 <style>/<script>，并转义内部 </script>。
        """
        try:
            html_content = (WEB_DIR / html_name).read_text(encoding='utf-8')
            css_content = (WEB_DIR / css_name).read_text(encoding='utf-8')
            js_content = (WEB_DIR / js_name).read_text(encoding='utf-8')
            config_path = WEB_DIR / 'config.js'
            config_content = config_path.read_text(encoding='utf-8') if config_path.exists() else ''

            html_content = html_content.replace(
                f'<link rel="stylesheet" href="{css_name}">',
                f'<style>{css_content}</style>'
            )
            if config_content:
                safe_config = config_content.replace('</script>', '<\\/script>')
                html_content = html_content.replace(
                    '<script src="config.js"></script>',
                    f'<script>{safe_config}</script>'
                )
            safe_js = js_content.replace('</script>', '<\\/script>')
            html_content = re.sub(
                r'<script src="' + re.escape(js_name) + r'(\?v=[^"]*)?"></script>',
                f'<script>{safe_js}</script>',
                html_content
            )

            body = html_content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            if no_cache:
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            _logger.exception(f"读取页面失败 html={html_name}: {e}")
            self.send_error_json('Read error', 500)

    def serve_index(self, query: Dict[str, Any]) -> None:
        """提供首页（CSS/JS内联，减少HTTP请求数）"""
        self._serve_inlined_page('index.html', 'style.css', 'app.js', no_cache=True)

    def serve_upload(self, query: Dict[str, Any]) -> None:
        """提供上传页（CSS/JS内联，减少HTTP请求数）"""
        self._serve_inlined_page('upload.html', 'upload.css', 'upload.js', no_cache=False)

    def serve_subscribe(self, query: Dict[str, Any]) -> None:
        """提供订阅介绍页（CSS/JS内联）"""
        self._serve_inlined_page('subscribe.html', 'subscribe.css', 'subscribe.js', no_cache=False)

    def serve_generate_license(self, query: Dict[str, Any]) -> None:
        """提供授权码生成器页面（位于项目根目录的独立工具页）"""
        from config import BASE_DIR
        self.serve_file(BASE_DIR.parent / 'generate_license.html', 'text/html')

    def serve_style(self, query: Dict[str, Any]) -> None:
        """提供样式文件"""
        self.serve_file(WEB_DIR / 'style.css', 'text/css')

    def serve_app_js(self, query: Dict[str, Any]) -> None:
        """提供应用JS"""
        self.serve_file(WEB_DIR / 'app.js', 'application/javascript')

    def serve_media_processor_js(self, query: Dict[str, Any]) -> None:
        """提供媒体处理JS"""
        self.serve_file(WEB_DIR / 'media-processor.js', 'application/javascript')

    def serve_vue_min(self, query: Dict[str, Any]) -> None:
        """提供Vue生产版"""
        self.serve_file(WEB_DIR / 'vue.global.min.js', 'application/javascript')
