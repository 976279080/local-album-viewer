#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库连接与事务装饰器"""

import sqlite3
import threading
from typing import Any, Callable

from config import DB_PATH

_db_lock = threading.RLock()
_wal_initialized = False
_init_lock = threading.Lock()


def _init_wal_mode(conn):
    """初始化WAL模式（仅执行一次）"""
    global _wal_initialized
    if _wal_initialized:
        return
    with _init_lock:
        if _wal_initialized:
            return
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA busy_timeout=5000')
        _wal_initialized = True


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    conn.row_factory = sqlite3.Row
    _init_wal_mode(conn)
    return conn


def _execute_with_lock(func: Callable) -> Any:
    """带锁执行数据库操作的装饰器"""
    def wrapper(*args, **kwargs):
        with _db_lock:
            return func(*args, **kwargs)
    return wrapper


def _db_transaction(func: Callable) -> Any:
    """事务装饰器

    若调用方未传入 conn，则新建连接并管理事务；
    若传入 conn，则复用调用方事务（不自动 commit/close）。
    无论哪种情况，都会通过 kwargs['cursor'] 注入游标。
    """
    def wrapper(*args, **kwargs):
        conn = None
        own_conn = False
        try:
            conn = kwargs.get('conn')
            if conn is None:
                conn = get_db_connection()
                own_conn = True
                conn.execute('BEGIN IMMEDIATE')

            cursor = conn.cursor()
            kwargs['cursor'] = cursor

            result = func(*args, **kwargs)

            if own_conn:
                conn.commit()
            return result
        except Exception as e:
            if own_conn and conn:
                conn.rollback()
            raise e
        finally:
            if own_conn and conn:
                conn.close()
    return wrapper


def _db_read(func: Callable) -> Any:
    """只读操作装饰器（WAL模式下读操作无需加锁）

    若调用方未传入 conn，则新建连接并管理关闭；
    若传入 conn，则复用调用方连接（不自动 close），便于批量场景共享事务。
    无论哪种情况，都会通过 kwargs['cursor'] 注入游标。
    """
    def wrapper(*args, **kwargs):
        conn = kwargs.get('conn')
        own_conn = False
        if conn is None:
            conn = get_db_connection()
            own_conn = True
        try:
            cursor = conn.cursor()
            kwargs['cursor'] = cursor
            return func(*args, **kwargs)
        finally:
            if own_conn:
                conn.close()
    return wrapper
