#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评论路由 Mixin - 通过 PhotoService 统一调用，避免 router 直连 db"""


class CommentRouterMixin:
    """评论 API 路由：list / add / delete"""

    def handle_comments(self, query) -> None:
        """获取照片评论列表"""
        photo_id = query.get('photo_id', [None])[0]
        if not photo_id:
            self.send_error_json('缺少photo_id参数')
            return

        try:
            comments = self.photo_service.get_comments(int(photo_id))
            self.send_json({'status': 'ok', 'comments': comments})
        except Exception as e:
            self.send_error_json(f'获取评论失败: {str(e)}')

    def handle_add_comment(self) -> None:
        """添加评论（评论操作无需密码鉴权）"""
        try:
            data = self.parse_request_body()
            photo_id = data.get('photo_id')
            text = data.get('text', '')

            if not photo_id:
                self.send_error_json('缺少photo_id参数')
                return
            if not text.strip():
                self.send_error_json('评论内容不能为空')
                return

            comment_id = self.photo_service.add_comment(int(photo_id), text.strip())
            self.send_json({'status': 'ok', 'comment_id': comment_id})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            self.send_error_json(f'添加评论失败: {str(e)}')

    def handle_delete_comment(self) -> None:
        """删除评论（需要密码鉴权）"""
        if not self.check_auth():
            return

        try:
            data = self.parse_request_body()
            comment_id = data.get('comment_id')

            if not comment_id:
                self.send_error_json('缺少comment_id参数')
                return

            self.photo_service.delete_comment(int(comment_id))
            self.send_json({'status': 'ok'})
        except ValueError as e:
            self.send_error_json(str(e))
        except Exception as e:
            self.send_error_json(f'删除评论失败: {str(e)}')
