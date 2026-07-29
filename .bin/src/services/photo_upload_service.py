#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片上传服务 - 封装照片上传相关业务逻辑
遵循单一职责原则：仅负责照片上传与缩略图保存
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import DATA_DIR, PREVIEW_DIR, ALLOWED_EXTS, IMAGE_EXTS, VIDEO_EXTS
from utils import get_file_extension, parse_image_size, parse_video_size, parse_iso_to_timestamp
from utils.mp4_faststart import is_fast_start, make_fast_start as mp4_make_fast_start
from db import (
    create_photo, update_photo as db_update_photo,
    get_album_by_id, add_tags_to_photo, get_summary,
    find_duplicate_photo,
)
from services._tag_helpers import ensure_tag_definition


class PhotoUploadService:
    """照片上传服务类"""

    def upload_photos(self, album_name: str, new_album_name: str, tags: List[str],
                      file_items: List[Dict[str, Any]], create_time_str: str,
                      width: str, height: str, file_size: str,
                      thumbnail_item: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
        """上传照片"""
        album_id, album_name, year, album_dir, meta = self._prepare_upload(
            album_name, new_album_name, create_time_str,
            width, height, file_size
        )
        w, h, ct, fsize = meta

        uploaded = []
        for item in file_items:
            result = self._upload_single_photo(
                album_id, album_name, year, album_dir,
                item, tags, thumbnail_item, w, h, ct, fsize
            )
            if result:
                uploaded.append(result)

        for tag in tags:
            ensure_tag_definition(tag)

        # 成功上传至少一张照片后，记录首次上传时间（仅第一次生效）
        if uploaded:
            self._record_first_upload()

        return uploaded

    def _prepare_upload(self, album_name: str, new_album_name: str,
                        create_time_str: str, width: str, height: str,
                        file_size: str) -> tuple:
        """上传前置准备：解析相册、年份、目录、元数据"""
        album_id = self._resolve_or_create_album(album_name, new_album_name)
        album_info = get_album_by_id(album_id)
        if not album_info:
            raise ValueError("相册不存在")

        album_name = album_info['name']
        year = self._parse_year(create_time_str)
        album_dir = self._ensure_album_year_dir(album_name, year)
        meta = self._parse_upload_metadata(width, height, create_time_str, file_size)

        return album_id, album_name, year, album_dir, meta

    def _upload_single_photo(self, album_id: int, album_name: str,
                             year: str, album_dir: Path, item: Dict[str, Any],
                             tags: List[str], thumbnail_item,
                             width: int, height: int, create_time: str,
                             file_size: int) -> Optional[Dict[str, str]]:
        """上传单张照片，返回 path_key 字典，失败返回 None"""
        if not self._is_valid_file_item(item):
            return None
        filename = item['filename']
        file_data = item['data']
        if not self._is_allowed_extension(filename):
            return None

        ext = get_file_extension(filename)
        file_size_val = file_size if file_size else len(file_data)

        w, h = width, height
        if w is None or h is None:
            ext_lower = ext.lower() if ext else ''
            if ext_lower in VIDEO_EXTS:
                w, h = parse_video_size(file_data, ext)
            else:
                w, h = parse_image_size(file_data, ext)

        create_time_ts = parse_iso_to_timestamp(create_time) if create_time else None
        if create_time_ts is None:
            create_time_ts = int(datetime.now().timestamp())

        year_int = int(year)

        dup = find_duplicate_photo(album_id, year_int, file_size_val, w, h)
        if dup:
            db_update_photo(dup['id'], update_time=int(datetime.now().timestamp()))
            return {
                'filename': dup['filename'],
                'path_key': f"{album_name}/{year}/{dup['filename']}",
                'duplicate': True
            }

        photo_id, new_filename = self._save_photo(
            album_id, filename, file_data, year, w, h,
            create_time_ts, file_size_val, album_dir, ext
        )

        if tags:
            add_tags_to_photo(photo_id, tags)

        if thumbnail_item:
            self._save_thumbnail(album_id, photo_id, thumbnail_item)

        return {
            'filename': new_filename,
            'path_key': f"{album_name}/{year}/{new_filename}"
        }

    @staticmethod
    def _record_first_upload() -> None:
        """记录首次上传时间（用于授权免费试用计算）"""
        try:
            from services.license_service import LicenseService
            LicenseService().record_first_upload()
        except Exception as e:
            print(f"记录首次上传时间失败: {e}")

    @staticmethod
    def _resolve_or_create_album(album_name: str, new_album_name: str) -> int:
        """解析或创建相册，返回相册ID

        并发上传时多个线程可能同时进入 create_album 导致"相册已存在"异常，
        此时重新查询即可拿到已创建的相册ID。
        """
        from services.album_service import AlbumService
        album_service = AlbumService()

        if new_album_name:
            try:
                return album_service.create_album(new_album_name)
            except ValueError:
                album_id = album_service.get_album_by_name(new_album_name)
                if album_id:
                    return album_id
                raise
        elif album_name:
            album_id = album_service.get_album_by_name(album_name)
            if album_id:
                return album_id
            try:
                return album_service.create_album(album_name)
            except ValueError:
                album_id = album_service.get_album_by_name(album_name)
                if album_id:
                    return album_id
                raise
        else:
            raise ValueError("请指定相册")

    @staticmethod
    def _parse_year(create_time_str: str) -> str:
        """解析年份"""
        now = datetime.now()
        if create_time_str:
            try:
                ct = datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))
                return str(ct.year)
            except Exception:
                pass
        return str(now.year)

    @staticmethod
    def _ensure_album_year_dir(album_name: str, year: str) -> Path:
        """确保相册年份目录存在"""
        album_dir = DATA_DIR / album_name / year
        album_dir.mkdir(parents=True, exist_ok=True)
        return album_dir

    @staticmethod
    def _parse_upload_metadata(width: str, height: str, create_time_str: str,
                               file_size: str) -> tuple:
        """解析上传元数据"""
        now = datetime.now()
        w = int(width) if width else None
        h = int(height) if height else None
        ct = create_time_str if create_time_str else now.isoformat()
        fsize = int(file_size) if file_size else 0
        return w, h, ct, fsize

    @staticmethod
    def _is_valid_file_item(item: Any) -> bool:
        """检查文件项是否有效"""
        return isinstance(item, dict) and 'filename' in item

    @staticmethod
    def _is_allowed_extension(filename: str) -> bool:
        """检查文件扩展名是否允许"""
        ext = get_file_extension(filename)
        return ext in ALLOWED_EXTS

    def _save_photo(self, album_id: int, filename: str, file_data: bytes, year: str,
                    width: int, height: int, create_time_ts: int,
                    file_size_val: int, album_dir: Path, ext: str) -> tuple:
        """保存照片到数据库和文件系统"""
        upload_time_ts = int(datetime.now().timestamp())

        ext_lower = ext.lower() if ext else ''
        if ext_lower in VIDEO_EXTS:
            file_type = 'video'
        else:
            file_type = 'image'

        photo_id = create_photo(
            album_id=album_id,
            filename='',
            year=int(year),
            title='',
            rating=0,
            size=file_size_val,
            width=width,
            height=height,
            file_type=file_type,
            create_time=create_time_ts,
            upload_time=upload_time_ts
        )

        new_filename = f"{photo_id}{ext}"
        file_path = album_dir / new_filename
        with open(file_path, 'wb') as f:
            f.write(file_data)

        if ext_lower == '.mp4':
            try:
                if not is_fast_start(file_path):
                    tmp_path = file_path.with_suffix('.tmp.mp4')
                    if mp4_make_fast_start(file_path, tmp_path):
                        tmp_path.replace(file_path)
                    else:
                        if tmp_path.exists():
                            tmp_path.unlink()
            except Exception:
                pass

        db_update_photo(photo_id, filename=new_filename)

        return photo_id, new_filename

    @staticmethod
    def _save_thumbnail(album_id: int, photo_id: int, thumbnail_item: Dict[str, Any]) -> None:
        """保存缩略图"""
        try:
            thumb_path = PREVIEW_DIR / f"{album_id}_{photo_id}.webp"
            with open(thumb_path, 'wb') as f:
                f.write(thumbnail_item['data'])
        except Exception as e:
            print(f"保存缩略图失败: {e}")
