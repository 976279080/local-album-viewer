#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
常量模块 - 集中管理散落在代码中的业务常量
遵循单一职责原则：仅负责常量定义
"""

# 相册颜色（创建相册时随机选择）
ALBUM_COLORS = [
    '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7',
    '#dda0dd', '#98d8c8', '#f7dc6f', '#bb8fce', '#85c1e9'
]

# 标签颜色（创建标签时随机选择）
TAG_COLORS = ['#4ecdc4', '#45b7d1', '#96ceb4', '#ff6b6b', '#feca57']

# SQLite IN 列表上限 999，分批处理时的批大小
TAG_BATCH_SIZE = 900

# 批量删除照片时的批大小（避免 SQLite 参数限制）
DELETE_BATCH_SIZE = 500

# 评论最大长度
MAX_COMMENT_LENGTH = 200

# 标题最大长度
MAX_TITLE_LENGTH = 15

# 拍摄时间最大修改次数
MAX_EDIT_COUNT = 2

# 文件命名非法字符集合（用于相册名/标题校验）
ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|.')

# 照片允许更新的字段（白名单，防止 SQL 注入与字段越权）
PHOTO_UPDATABLE_FIELDS = (
    'title', 'rating', 'size', 'width', 'height',
    'create_time', 'update_time', 'filename',
)

# 相册允许更新的字段
ALBUM_UPDATABLE_FIELDS = ('name', 'color')

# 默认分页大小
DEFAULT_PAGE_SIZE = 200

# 全量查询时使用的大页码（避免使用 LIMIT 限制）
MAX_PAGE_SIZE = 100000

# 默认相册/标签颜色
DEFAULT_COLOR = '#999999'
