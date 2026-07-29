#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签相关公共辅助函数

抽出 PhotoUploadService / PhotoUpdateService / PhotoTagService / PhotoDeleteService
中重复的 _ensure_tag_definition 与 _cleanup_unused_tags 实现，统一通过 AlbumService
调用，避免每个 service 各自 new AlbumService() 并重复同样的转发代码。

放在独立模块亦能打破 service 之间的循环 import（album_service 反向依赖可在此处集中处理）。
"""




def ensure_tag_definition(tag_name: str) -> None:
    """确保标签定义存在（不存在则创建）"""
    # 延迟 import 避免 services 包内循环依赖
    from services.album_service import AlbumService
    AlbumService().add_tag_definition(tag_name)


def cleanup_unused_tags() -> None:
    """清理未被任何照片引用的标签"""
    from services.album_service import AlbumService
    AlbumService().cleanup_unused_tags()
