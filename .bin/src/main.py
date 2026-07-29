#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无联网相册 - 主启动入口
负责初始化、启动HTTP服务
"""

import time
import socketserver

from config import SERVER_PORT, init_dirs
from handler import PhotoHandler
from utils import init_logging, get_logger


init_dirs()
init_logging()
logger = get_logger('main')

server_start_time = 0


def run_server():
    """启动服务器"""
    global server_start_time
    server_start_time = time.time()

    class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        request_queue_size = 128
        daemon_threads = True

    server = ThreadedHTTPServer(('0.0.0.0', SERVER_PORT), PhotoHandler)
    logger.info(f"服务已启动: http://localhost:{SERVER_PORT}")

    server.serve_forever()


def init_db():
    """初始化数据库"""
    from db import init_database
    init_database()
    logger.info("数据库初始化完成")


if __name__ == '__main__':
    init_db()
    run_server()