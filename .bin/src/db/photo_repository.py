#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片数据访问层"""

from typing import Dict, Any, List, Optional

from constants import TAG_BATCH_SIZE, PHOTO_UPDATABLE_FIELDS
from utils import get_current_time

from .connection import _db_transaction, _db_read


@_db_transaction
def create_photo(album_id: int, filename: str, year: int,
                 title: str = '', rating: int = 0, size: int = 0, width: int = None,
                 height: int = None, file_type: str = 'image',
                 create_time: int = None, upload_time: int = None, **kwargs) -> int:
    """创建照片记录，返回照片ID"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT id FROM albums WHERE id = ?', (album_id,))
    if not cursor.fetchone():
        raise ValueError("相册不存在")

    now = get_current_time()
    upload_time = upload_time or now
    update_time = now

    cursor.execute('''
        INSERT INTO photos (album_id, filename, year, title,
                           rating, size, width, height, file_type, create_time,
                           upload_time, update_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (album_id, filename, year, title,
          rating, size, width, height, file_type, create_time, upload_time, update_time))

    photo_id = cursor.lastrowid

    # 同步更新 albums.latest_upload（应用层维护，避免聚合查询）
    cursor.execute('UPDATE albums SET latest_upload = ? WHERE id = ? AND COALESCE(latest_upload, 0) < ?',
                   (upload_time, album_id, upload_time))

    return photo_id


@_db_read
def get_photo_by_id(photo_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """根据ID获取照片信息"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM photos WHERE id = ?', (photo_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def find_duplicate_photo(album_id: int, year: int, size: int, width: int, height: int, **kwargs) -> Optional[Dict[str, Any]]:
    """查找重复照片（同相册、同年份、同大小、同尺寸）"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT * FROM photos
        WHERE album_id = ? AND year = ? AND size = ? AND width = ? AND height = ?
        LIMIT 1
    ''', (album_id, year, size, width, height))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_photo_by_path(album_id: int, year: str, filename: str, **kwargs) -> Optional[Dict[str, Any]]:
    """根据相册ID、年份、文件名获取照片（使用索引查询）"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT * FROM photos WHERE album_id = ? AND year = ? AND filename = ?',
                   (album_id, year, filename))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_photos_by_album(album_id: int, year: int = None, **kwargs) -> List[Dict[str, Any]]:
    """获取指定相册的照片列表"""
    cursor = kwargs['cursor']

    if year:
        cursor.execute('''
            SELECT * FROM photos WHERE album_id = ? AND year = ?
            ORDER BY create_time DESC
        ''', (album_id, year))
    else:
        cursor.execute('''
            SELECT * FROM photos WHERE album_id = ?
            ORDER BY year DESC, create_time DESC
        ''', (album_id,))

    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_read
def get_all_photos_with_pagination(filters: Dict[str, Any] = None, page: int = 1, page_size: int = 200,
                                   sort_by: str = 'capture_time', sort_order: str = 'desc',
                                   photo_type: str = 'all', **kwargs) -> Dict[str, Any]:
    """获取所有照片（支持筛选、排序、分页）"""
    cursor = kwargs['cursor']

    select_fields = '''
        p.id, p.album_id, p.filename, p.year, p.title, p.rating,
        p.tag_count, p.comment_count, p.size, p.width, p.height, p.file_type,
        p.create_time, p.upload_time, p.update_time,
        a.name as album_name, a.color as album_color
    '''

    sql = f'''
        SELECT {select_fields}
        FROM photos p
        LEFT JOIN albums a ON p.album_id = a.id
    '''

    count_sql = 'SELECT COUNT(*) as cnt FROM photos p'

    params = []
    conditions = []

    if filters:
        if 'album_id' in filters and filters['album_id']:
            conditions.append('p.album_id = ?')
            params.append(filters['album_id'])

        if 'year' in filters and filters['year']:
            conditions.append('p.year = ?')
            params.append(filters['year'])

        if 'rating' in filters and filters['rating'] is not None:
            rating = filters['rating']
            if rating == 'positive':
                conditions.append('p.rating > 0')
            elif rating == 'negative':
                conditions.append('p.rating < 0')
            elif rating == 'neutral':
                conditions.append('p.rating = 0')
            else:
                try:
                    conditions.append('p.rating = ?')
                    params.append(int(rating))
                except ValueError:
                    pass

        if 'tag' in filters and filters['tag']:
            # 使用 EXISTS 子查询替代 JOIN+DISTINCT，避免重复行和大量数据扫描
            conditions.append('''EXISTS (
                SELECT 1 FROM photo_tags pt
                JOIN tags t ON pt.tag_id = t.id
                WHERE pt.photo_id = p.id AND t.name = ?
            )''')
            params.append(filters['tag'])

    if photo_type and photo_type != 'all':
        # 使用 file_type 字段索引替代 LOWER(filename) LIKE
        if photo_type == 'image':
            conditions.append("p.file_type = 'image'")
        elif photo_type == 'video':
            conditions.append("p.file_type = 'video'")

    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
        count_sql += ' WHERE ' + ' AND '.join(conditions)

    sort_column = 'p.create_time'
    if sort_by == 'update_time':
        sort_column = 'p.update_time'
    sort_dir = 'DESC' if sort_order == 'desc' else 'ASC'
    sql += f' ORDER BY {sort_column} {sort_dir}'

    sql += ' LIMIT ? OFFSET ?'

    cursor.execute(count_sql, params)
    total = cursor.fetchone()['cnt']

    offset = (page - 1) * page_size
    cursor.execute(sql, params + [page_size, offset])
    rows = cursor.fetchall()

    return {
        'photos': [dict(row) for row in rows],
        'total': total,
        'page': page,
        'page_size': page_size
    }


@_db_read
def get_all_photos_with_details(**kwargs) -> Dict[str, Any]:
    """批量获取所有照片及其标签和评论（优化版，分批避免 IN 列表超 999 上限）"""
    cursor = kwargs['cursor']

    cursor.execute('''
        SELECT p.id, p.album_id, p.filename, p.year, p.title, p.rating,
               p.tag_count, p.comment_count, p.size, p.width, p.height, p.file_type,
               p.create_time, p.upload_time, p.update_time,
               a.name as album_name, a.color as album_color
        FROM photos p
        LEFT JOIN albums a ON p.album_id = a.id
        ORDER BY p.create_time DESC
    ''')
    rows = cursor.fetchall()
    photos = [dict(row) for row in rows]

    photo_ids = [p['id'] for p in photos]
    photo_tags = {}
    photo_comments = {}

    # SQLite 默认 IN 列表上限 999，分批处理
    for i in range(0, len(photo_ids), TAG_BATCH_SIZE):
        batch = photo_ids[i:i + TAG_BATCH_SIZE]
        placeholders = ','.join(['?'] * len(batch))
        cursor.execute(f'''
            SELECT pt.photo_id, t.name, t.color
            FROM photo_tags pt
            JOIN tags t ON pt.tag_id = t.id
            WHERE pt.photo_id IN ({placeholders})
            ORDER BY t.name
        ''', batch)
        for row in cursor.fetchall():
            pid = row['photo_id']
            if pid not in photo_tags:
                photo_tags[pid] = []
            photo_tags[pid].append({'name': row['name'], 'color': row['color']})

        cursor.execute(f'''
            SELECT photo_id, text, created_at
            FROM comments
            WHERE photo_id IN ({placeholders})
            ORDER BY created_at DESC
        ''', batch)
        for row in cursor.fetchall():
            pid = row['photo_id']
            if pid not in photo_comments:
                photo_comments[pid] = []
            photo_comments[pid].append({
                'text': row['text'],
                'created_at': row['created_at']
            })

    return {
        'photos': photos,
        'tags': photo_tags,
        'comments': photo_comments
    }


@_db_transaction
def update_photo(photo_id: int, **kwargs) -> bool:
    """更新照片信息"""
    cursor = kwargs['cursor']

    cursor.execute('SELECT * FROM photos WHERE id = ?', (photo_id,))
    if not cursor.fetchone():
        raise ValueError("照片不存在")

    updates = []
    params = []

    for field in PHOTO_UPDATABLE_FIELDS:
        if field in kwargs:
            updates.append(f'{field} = ?')
            params.append(kwargs[field])

    if updates:
        updates.append('update_time = ?')
        params.append(get_current_time())
        params.append(photo_id)

        sql = f'UPDATE photos SET {", ".join(updates)} WHERE id = ?'
        cursor.execute(sql, params)

    return True


@_db_transaction
def delete_photo_records(photo_id: int, **kwargs) -> Dict[str, Any]:
    """删除照片的数据库记录（不操作文件系统）

    Returns:
        包含 album_name/year/filename 的字典，供 service 层清理文件
    """
    cursor = kwargs['cursor']

    cursor.execute('SELECT filename, year, album_id FROM photos WHERE id = ?', (photo_id,))
    photo = cursor.fetchone()
    if not photo:
        raise ValueError("照片不存在")

    cursor.execute('SELECT name FROM albums WHERE id = ?', (photo['album_id'],))
    album = cursor.fetchone()
    album_name = album['name'] if album else ''

    cursor.execute('DELETE FROM comments WHERE photo_id = ?', (photo_id,))
    cursor.execute('DELETE FROM photo_tags WHERE photo_id = ?', (photo_id,))
    cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))

    return {
        'album_name': album_name,
        'year': photo['year'],
        'filename': photo['filename'],
    }


@_db_read
def get_photo_count(album_id: int = None, **kwargs) -> Dict[str, Any]:
    """获取照片数量统计"""
    cursor = kwargs['cursor']

    counts = {'total': 0, 'by_album': {}, 'by_year': {}, 'by_album_year': {}}

    if album_id:
        cursor.execute('''
            SELECT year, COUNT(*) as cnt FROM photos
            WHERE album_id = ? GROUP BY year
        ''', (album_id,))
        rows = cursor.fetchall()
        total = 0
        counts['by_album_year'][album_id] = {}
        for row in rows:
            year = row['year']
            cnt = row['cnt']
            counts['by_year'][year] = cnt
            counts['by_album_year'][album_id][year] = cnt
            total += cnt
        counts['total'] = total
        counts['by_album'][album_id] = total
    else:
        cursor.execute('''
            SELECT p.album_id, p.year, COUNT(*) as cnt FROM photos p
            GROUP BY p.album_id, p.year
        ''')
        rows = cursor.fetchall()
        for row in rows:
            aid = row['album_id']
            year = row['year']
            cnt = row['cnt']

            counts['by_album'][aid] = counts['by_album'].get(aid, 0) + cnt
            counts['by_year'][year] = counts['by_year'].get(year, 0) + cnt
            if aid not in counts['by_album_year']:
                counts['by_album_year'][aid] = {}
            counts['by_album_year'][aid][year] = cnt
            counts['total'] += cnt

    return counts


@_db_read
def count_photos_by_album(album_id: int, **kwargs) -> int:
    """统计指定相册的照片数量"""
    cursor = kwargs['cursor']
    cursor.execute('SELECT COUNT(*) as cnt FROM photos WHERE album_id = ?', (album_id,))
    row = cursor.fetchone()
    return row['cnt'] if row else 0


@_db_read
def get_photo_with_album(photo_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """根据ID获取照片信息（包含相册名称和颜色）"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT p.*, a.name as album_name, a.color as album_color
        FROM photos p
        LEFT JOIN albums a ON p.album_id = a.id
        WHERE p.id = ?
    ''', (photo_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


@_db_read
def get_photo_tags_with_color(photo_id: int, **kwargs) -> List[Dict[str, Any]]:
    """获取照片的所有标签（包含颜色）"""
    cursor = kwargs['cursor']
    cursor.execute('''
        SELECT t.name, t.color
        FROM photo_tags pt
        JOIN tags t ON pt.tag_id = t.id
        WHERE pt.photo_id = ?
        ORDER BY t.name
    ''', (photo_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


@_db_transaction
def batch_delete_photos(photo_ids: List[int], **kwargs) -> None:
    """批量删除照片的数据库记录（分批避免 SQLite 参数上限）"""
    cursor = kwargs['cursor']
    from constants import DELETE_BATCH_SIZE

    if not photo_ids:
        return

    for i in range(0, len(photo_ids), DELETE_BATCH_SIZE):
        batch = photo_ids[i:i + DELETE_BATCH_SIZE]
        placeholders = ','.join(['?'] * len(batch))
        cursor.execute(f'DELETE FROM comments WHERE photo_id IN ({placeholders})', batch)
        cursor.execute(f'DELETE FROM photo_tags WHERE photo_id IN ({placeholders})', batch)
        cursor.execute(f'DELETE FROM photos WHERE id IN ({placeholders})', batch)

    cursor.execute('''
        DELETE FROM tags
        WHERE NOT EXISTS (SELECT 1 FROM photo_tags WHERE tag_id = tags.id)
    ''')


@_db_transaction
def update_photo_create_time(photo_id: int, create_time: int, year: int, edit_count: int, **kwargs) -> None:
    """更新照片的拍摄时间和年份"""
    cursor = kwargs['cursor']
    from utils import get_current_time

    cursor.execute('''
        UPDATE photos
        SET create_time = ?, year = ?, update_time = ?, edit_count = ?
        WHERE id = ?
    ''', (create_time, year, get_current_time(), edit_count + 1, photo_id))
