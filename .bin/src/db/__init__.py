#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库子包 - re-export 所有 db 函数，保持 `from db import xxx` 可用
实际实现分布在 connection / schema / *_repository 模块
"""

# 连接与事务装饰器
from .connection import (
    _db_lock,
    get_db_connection,
    _execute_with_lock,
    _db_transaction,
    _db_read,
)

# 表结构
from .schema import init_database, init_database_with_conn

# 相册仓库
from .album_repository import (
    create_album,
    get_album_by_id,
    get_album_by_name,
    get_all_albums,
    update_album,
    rename_album_records,
    delete_album_records,
)

# 照片仓库
from .photo_repository import (
    create_photo,
    get_photo_by_id,
    get_photo_by_path,
    get_photos_by_album,
    get_all_photos_with_pagination,
    get_all_photos_with_details,
    update_photo,
    delete_photo_records,
    get_photo_count,
    count_photos_by_album,
    get_photo_with_album,
    get_photo_tags_with_color,
    batch_delete_photos,
    update_photo_create_time,
    find_duplicate_photo,
)

# 标签仓库
from .tag_repository import (
    create_tag,
    get_tag_by_id,
    get_tag_by_name,
    get_all_tags,
    delete_tag,
    cleanup_unused_tags,
    add_tags_to_photo,
    remove_tags_from_photo,
    get_photo_tags,
    batch_get_photo_tags,
    batch_add_tags_to_photos,
    batch_remove_tags_from_photos,
)

# 评论仓库
from .comment_repository import (
    add_comment,
    delete_comment,
    get_photo_comments,
    delete_all_comments,
    batch_add_comments,
)

# 统计仓库
from .summary_repository import get_summary, get_years

# 系统配置仓库
from .system_config_repository import (
    get_config,
    set_config,
    get_all_config,
    delete_config,
)

__all__ = [
    # connection
    '_db_lock', 'get_db_connection', '_execute_with_lock', '_db_transaction', '_db_read',
    # schema
    'init_database', 'init_database_with_conn',
    # album_repository
    'create_album', 'get_album_by_id', 'get_album_by_name', 'get_all_albums',
    'update_album', 'rename_album_records', 'delete_album_records',
    # photo_repository
    'create_photo', 'get_photo_by_id', 'get_photo_by_path', 'get_photos_by_album',
    'get_all_photos_with_pagination', 'get_all_photos_with_details',
    'update_photo', 'delete_photo_records',
    'get_photo_count', 'count_photos_by_album',
    'get_photo_with_album', 'get_photo_tags_with_color',
    'batch_delete_photos', 'update_photo_create_time', 'find_duplicate_photo',
    # tag_repository
    'create_tag', 'get_tag_by_id', 'get_tag_by_name', 'get_all_tags',
    'delete_tag', 'cleanup_unused_tags', 'add_tags_to_photo',
    'remove_tags_from_photo', 'get_photo_tags', 'batch_get_photo_tags',
    # comment_repository
    'add_comment', 'delete_comment', 'get_photo_comments', 'delete_all_comments', 'batch_add_comments',
    # summary_repository
    'get_summary', 'get_years',
    # tag_repository batch
    'batch_add_tags_to_photos', 'batch_remove_tags_from_photos',
    # system_config_repository
    'get_config', 'set_config', 'get_all_config', 'delete_config',
]
