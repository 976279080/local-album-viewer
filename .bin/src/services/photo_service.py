#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片服务模块 - 门面模式，组合各子服务
遵循单一职责原则：仅负责组合子服务，提供统一接口
实际业务逻辑分布在各子服务中：
  - PhotoQueryService: 查询与数据组装
  - PhotoUploadService: 上传与缩略图
  - PhotoDeleteService: 删除与清理
  - PhotoUpdateService: 元数据更新
  - PhotoTagService: 标签批量操作
  - PhotoCommentService: 评论操作
"""

from typing import Dict, Any, List, Optional

from services.photo_query_service import PhotoQueryService
from services.photo_upload_service import PhotoUploadService
from services.photo_delete_service import PhotoDeleteService
from services.photo_update_service import PhotoUpdateService
from services.photo_tag_service import PhotoTagService
from services.photo_comment_service import PhotoCommentService


class PhotoService:
    """照片服务类（门面模式）

    门面只暴露外部路由/处理器需要的统一接口；各子服务的私有 _xxx 方法
    不再通过此门面转发，调用方应直接使用子服务实例。
    """

    def __init__(self):
        self._query_service = PhotoQueryService()
        self._upload_service = PhotoUploadService()
        self._delete_service = PhotoDeleteService()
        self._update_service = PhotoUpdateService(query_service=self._query_service)
        self._tag_service = PhotoTagService(delete_service=self._delete_service)
        self._comment_service = PhotoCommentService()

    # ===== 查询相关（委托给 PhotoQueryService）=====

    def get_photo_count(self, album_id: Optional[str] = None) -> Dict[str, Any]:
        """获取照片数量统计"""
        return self._query_service.get_photo_count(album_id)

    def get_album_years(self, album_id: str) -> Dict[str, Any]:
        """获取相册的年份列表及各年份照片数"""
        return self._query_service.get_album_years(album_id)

    def get_photos(self, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取照片列表（支持筛选和分页）"""
        return self._query_service.get_photos(filters)

    def get_photo_detail(self, photo_id: int) -> Dict[str, Any]:
        """获取单张照片详情（含标签和评论）"""
        return self._query_service.get_photo_detail(photo_id)

    # ===== 上传相关（委托给 PhotoUploadService）=====

    def upload_photos(self, album_name: str, new_album_name: str, tags: List[str],
                      file_items: List[Dict[str, Any]], create_time_str: str,
                      width: str, height: str, file_size: str,
                      thumbnail_item: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
        """上传照片"""
        return self._upload_service.upload_photos(
            album_name, new_album_name, tags, file_items,
            create_time_str, width, height, file_size,
            thumbnail_item
        )

    # ===== 删除相关（委托给 PhotoDeleteService）=====

    def delete_photo(self, path_key_or_id) -> None:
        """删除单张照片"""
        self._delete_service.delete_photo(path_key_or_id)

    def batch_delete(self, path_keys: List[str]) -> Dict[str, Any]:
        """批量删除照片"""
        return self._delete_service.batch_delete(path_keys)

    # ===== 更新相关（委托给 PhotoUpdateService）=====

    def update_photo(self, path_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新照片元数据"""
        return self._update_service.update_photo(path_key, data)

    # ===== 标签相关（委托给 PhotoTagService）=====

    def batch_tag(self, path_keys: List[str], tags: List[str]) -> Dict[str, Any]:
        """批量打标签"""
        return self._tag_service.batch_tag(path_keys, tags)

    def batch_clear_tags(self, path_keys: List[str]) -> Dict[str, Any]:
        """批量清空标签"""
        return self._tag_service.batch_clear_tags(path_keys)

    # ===== 评论相关（委托给 PhotoCommentService）=====

    def get_comments(self, photo_id: int) -> List[Dict[str, Any]]:
        """获取照片评论列表"""
        return self._comment_service.get_comments(photo_id)

    def add_comment(self, photo_id: int, text: str) -> int:
        """添加评论"""
        return self._comment_service.add_comment(photo_id, text)

    def delete_comment(self, comment_id: int) -> None:
        """删除评论"""
        self._comment_service.delete_comment(comment_id)
