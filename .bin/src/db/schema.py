#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库表结构定义与初始化"""

from .connection import _execute_with_lock, get_db_connection


def _create_schema(cursor) -> None:
    """在给定游标上创建所有表和索引（不负责事务/关闭连接）"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#999999',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            latest_upload INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_name ON albums(name)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            year INTEGER NOT NULL,
            title TEXT DEFAULT '',
            rating INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            tag_count INTEGER DEFAULT 0,
            size INTEGER DEFAULT 0,
            width INTEGER,
            height INTEGER,
            file_type TEXT DEFAULT 'image',
            create_time INTEGER,
            upload_time INTEGER NOT NULL,
            update_time INTEGER NOT NULL,
            edit_count INTEGER DEFAULT 0
        )
    ''')
    # 单列索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_year ON photos(year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_rating ON photos(rating)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_update_time ON photos(update_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_file_type ON photos(file_type)')
    # 复合索引（覆盖主要查询路径）
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_album_year_filename ON photos(album_id, year, filename)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_album_year_create_time ON photos(album_id, year, create_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photos_album_create_time ON photos(album_id, create_time)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#999999'
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photo_tags (
            photo_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (photo_id, tag_id)
        )
    ''')
    # 反向查询：按 tag_id 查照片
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_photo_tags_tag_id_photo_id ON photo_tags(tag_id, photo_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_photo_id ON comments(photo_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    ''')


def _migrate_schema(cursor) -> None:
    """增量字段迁移：为已存在的表补齐后续新增字段（不破坏现有数据）"""
    # 检查 photos 表是否有 edit_count 列
    cursor.execute("PRAGMA table_info(photos)")
    columns = {row[1] for row in cursor.fetchall()}
    if 'edit_count' not in columns:
        cursor.execute("ALTER TABLE photos ADD COLUMN edit_count INTEGER DEFAULT 0")

    # 授权相关配置：首次部署时写入默认种子值（明文存储于 system_config 表）
    # 后续可在数据库中直接修改这些值，代码运行时只读取、不再硬编码
    _seed_license_config(cursor)


def _seed_license_config(cursor) -> None:
    """首次初始化时写入授权配置默认值（已存在的键不覆盖）

    默认值以密文形式硬编码在源码中，运行时解密后写入数据库（数据库明文存储）。
    修改默认值：用 utils.crypto_util.obfuscate() 生成新密文替换即可。
    """
    from utils import get_current_time
    from utils.crypto_util import deobfuscate

    # (配置键, 默认值的密文) —— 源码不暴露明文
    defaults = [
        ('license_secret_key', deobfuscate('EAsfDQtKZ1Q=')),
        ('free_trial_days', deobfuscate('SF8=')),
        ('license_monthly_days', deobfuscate('Ql4=')),
        ('license_yearly_days', deobfuscate('QllH')),
    ]
    now = get_current_time()
    for key, value in defaults:
        cursor.execute('SELECT 1 FROM system_config WHERE key = ?', (key,))
        if cursor.fetchone() is None:
            cursor.execute(
                'INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, ?)',
                (key, value, now)
            )


def init_database_with_conn(conn) -> None:
    """使用外部传入的连接初始化 schema（不负责 commit/close，由调用方管理）

    适用于测试场景下复用内存 SQLite 连接。
    """
    cursor = conn.cursor()
    _create_schema(cursor)
    _migrate_schema(cursor)
    conn.commit()


@_execute_with_lock
def init_database() -> None:
    """初始化数据库表结构（自带连接管理）"""
    conn = get_db_connection()
    try:
        init_database_with_conn(conn)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
