#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由子包 - re-export 所有 Router Mixin
PhotoHandler 通过多继承组合这些 Mixin 实现方法分发
"""

from .auth_middleware import check_auth
from .static_router import StaticRouterMixin
from .photo_router import PhotoRouterMixin
from .album_router import AlbumRouterMixin
from .upload_router import UploadRouterMixin
from .comment_router import CommentRouterMixin
from .version_router import VersionRouterMixin
from .license_router import LicenseRouterMixin

__all__ = [
    'check_auth',
    'StaticRouterMixin',
    'PhotoRouterMixin',
    'AlbumRouterMixin',
    'UploadRouterMixin',
    'CommentRouterMixin',
    'VersionRouterMixin',
    'LicenseRouterMixin',
]
