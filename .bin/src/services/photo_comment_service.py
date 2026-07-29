#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片评论服务 - 封装照片评论相关业务逻辑
遵循单一职责原则：仅负责照片评论的增删查
"""

from typing import Dict, Any, List

from db import add_comment, delete_comment, get_photo_comments


class PhotoCommentService:
    """照片评论服务类"""

    def get_comments(self, photo_id: int) -> List[Dict[str, Any]]:
        """获取照片评论列表"""
        return get_photo_comments(photo_id)

    def add_comment(self, photo_id: int, text: str) -> int:
        """添加评论"""
        return add_comment(photo_id, text)

    def delete_comment(self, comment_id: int) -> None:
        """删除评论"""
        delete_comment(comment_id)
