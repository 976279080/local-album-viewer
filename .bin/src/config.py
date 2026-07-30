#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块 - 集中管理所有常量、路径和全局设置
遵循单一职责原则：仅负责配置定义和初始化
"""

import os
from pathlib import Path

_env_base_dir = os.environ.get('QORDER_BASE_DIR')
if _env_base_dir:
    BASE_DIR = Path(_env_base_dir) / ".bin"
else:
    BASE_DIR = Path(__file__).parent.parent

DATA_DIR = BASE_DIR.parent / "data"
USER_DATA_DIR = BASE_DIR.parent / ".user_data"
PREVIEW_DIR = USER_DATA_DIR / "previews"
WEB_DIR = BASE_DIR / "web"
IMAGES_DIR = WEB_DIR / "images"
DB_DIR = USER_DATA_DIR / "db"
DB_PATH = DB_DIR / "album.db"

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v', '.3gp'}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS

EXCLUDED_DIRS = {'python', '.venv', 'venv', '__pycache__', '.bin', '.user_data'}

PREVIEW_MAX_WIDTH = 300
PREVIEW_QUALITY = 60

SERVER_PORT = 8089

# 访问密码（用于修改类操作的鉴权）
# 修改后需重启服务生效
PASSWORD = '111222'


def init_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)


# 版本检查配置
GITEE_RAW_BASE = 'https://gitee.com/cdgm/local-album-viewer/raw/main'  # 码云 raw 地址
VERSION_JSON_PATH = 'version.json'  # version.json 相对路径
VERSION_CHECK_TIMEOUT = 5  # 版本检查超时时间（秒）

# 首次进入引导遮罩
# True: 无论是否已有照片，都强制显示首次引导弹窗（方便测试）
# False: 仅在没有照片时自动显示引导（正常逻辑）
FORCE_FIRST_TIME_GUIDE = False


