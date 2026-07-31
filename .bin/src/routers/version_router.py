#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本检查路由 Mixin"""

from services.version_service import VersionService


class VersionRouterMixin:
    """版本检查 API 路由：check, list, download"""

    def handle_version_list(self, query) -> None:
        """GET /api/version/list - 获取完整版本列表（无需认证）"""
        try:
            svc = VersionService()
            result = svc.get_version_list()
            self.send_json({'status': 'ok', **result})
        except Exception as e:
            self.send_error_json(f'获取版本列表失败: {str(e)}')

    def handle_version_check(self, query) -> None:
        """GET /api/version/check - 检查版本更新（无需认证）"""
        try:
            svc = VersionService()
            result = svc.check_version()
            self.send_json({'status': 'ok', **result})
        except Exception as e:
            self.send_error_json(f'版本检查失败: {str(e)}')

    def handle_version_download(self) -> None:
        """POST /api/version/download - 下载并准备更新包（需密码认证）

        请求体：{ "download_url": str, "version": str }
        下载与解压可能耗时较长（几秒到几十秒），由前端展示 loading 状态。
        """
        try:
            if not self.check_auth():
                return
            try:
                body = self.parse_request_body()
            except ValueError:
                self.send_error_json('请求体格式错误')
                return
            download_url = str(body.get('download_url', '') or '').strip()
            target_version = str(body.get('version', '') or '').strip()
            if not download_url:
                self.send_error_json('缺少 download_url 参数')
                return

            svc = VersionService()
            result = svc.download_update(download_url, target_version)
            if result.get('success'):
                self.send_json({'status': 'ok', **result})
            else:
                self.send_json({'status': 'error', **result}, status=400)
        except Exception as e:
            self.send_error_json(f'准备更新失败: {str(e)}')

    def handle_version_trigger_restart(self) -> None:
        """POST /api/version/trigger-restart - 触发服务重启并应用待处理更新（需认证）

        请求体（可选）：{ "open_url_path": "/upload.html", "port": 8089 }
        流程：
          1) 响应 JSON { success: true, ok: true, message: '...', restart_in_ms: 1400 }
             → 确保父 HTTP 响应先通过 wfile.write 发送完整
          2) fork 启动 restarter.py（带 --kill-parent <pid> + --delay-before-kill 1.2s + --port <port>）
          3) 自己 os._exit(0)：由 restarter 在 1.2s 后杀本进程、清端口、应用更新、拉起新服务
        """
        try:
            if not self.check_auth():
                return
            try:
                body = self.parse_request_body()
            except (ValueError, Exception):
                body = {}
            if not isinstance(body, dict):
                body = {}

            import os
            import sys
            import subprocess
            from pathlib import Path

            port = int(body.get('port') or 8089)
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            restarter_py = project_root / '.bin' / 'src' / 'restarter.py'
            python_bin = sys.executable or 'python3'

            # 1) 先把响应完整写出去（Content-Length 已知，wfile 立即 flush）
            payload_body = {
                'status': 'ok',
                'success': True,
                'ok': True,
                'restart_required': True,
                'restart_in_ms': 1400,
                'message': '准备重启并应用更新，服务将在 1~2 秒后重新上线',
                'port': port,
            }
            import json as _json
            body_bytes = _json.dumps(payload_body, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            try:
                self.wfile.write(body_bytes)
                self.wfile.flush()
            except Exception:
                pass

            # 2) fork 启动 restarter（不阻塞 HTTP 响应）
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            cmd = [
                python_bin,
                str(restarter_py),
                '--delay-before-kill', '1.2',
                '--port', str(port),
                '--kill-parent', str(os.getpid()),
            ]
            try:
                if sys.platform == 'darwin' or os.name == 'posix':
                    log_path = project_root / '.user_data' / 'restarter.log'
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    fp = open(log_path, 'ab')
                    subprocess.Popen(
                        cmd,
                        cwd=str(project_root),
                        stdout=fp,
                        stderr=subprocess.STDOUT,
                        env=env,
                        start_new_session=True,
                    )
                elif sys.platform.startswith('win'):
                    DETACHED_PROCESS = 0x00000008
                    CREATE_NEW_PROCESS_GROUP = 0x00000200
                    log_path = project_root / '.user_data' / 'restarter.log'
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    fp = open(log_path, 'ab')
                    subprocess.Popen(
                        cmd,
                        cwd=str(project_root),
                        stdout=fp,
                        stderr=subprocess.STDOUT,
                        env=env,
                        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    )
                else:
                    subprocess.Popen(cmd, cwd=str(project_root), env=env)
            except Exception as ex:
                try:
                    # 兜底：直接把触发失败信息再写回一个额外响应标记（其实写不写都一样）
                    pass
                except Exception:
                    pass
                # 失败了也要退出，但要让上层知道
                err_msg = f'[trigger-restart] fork restarter 失败: {ex}'
                sys.stderr.write(err_msg + '\n')
                sys.stderr.flush()

            # 3) 自己退出（restarter 会在 1.2s 后 kill 这个父进程；这里提前退出避免它再写别的请求）
            try:
                import threading
                def _suicide():
                    import time as _t
                    _t.sleep(0.05)
                    os._exit(0)
                threading.Thread(target=_suicide, daemon=True).start()
            except Exception:
                os._exit(0)

        except Exception as e:
            try:
                self.send_error_json(f'触发重启失败: {str(e)}')
            except Exception:
                pass
