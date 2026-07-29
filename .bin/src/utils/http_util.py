#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 协议工具函数"""

from typing import Dict, Any


def parse_multipart(data: bytes, boundary: str) -> Dict[str, Any]:
    """解析 multipart/form-data 格式数据

    Args:
        data: HTTP请求体原始数据
        boundary: multipart边界字符串

    Returns:
        解析后的字段字典，文件字段值为 {'filename': str, 'data': bytes}
    """
    result = {}
    boundary_bytes = b'--' + boundary.encode('utf-8')

    parts = data.split(boundary_bytes)
    for part in parts:
        if not part.strip():
            continue

        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue

        headers = part[:header_end].decode('utf-8', errors='replace')
        body = part[header_end + 4:]

        # part 结构: \r\n<headers>\r\n\r\n<body>\r\n
        # body 末尾的 \r\n 是 multipart part 的结束标志，需要去掉
        # 注意：不能在 body 内部搜索特定字节序列（如 \r\n--\r\n），
        # 因为二进制文件（视频/图片）可能包含该序列，会导致文件被截断
        if body.endswith(b'\r\n'):
            body = body[:-2]

        filename = None
        field_name = None

        for line in headers.split('\r\n'):
            if line.lower().startswith('content-disposition:'):
                attrs = _parse_content_disposition(line)
                field_name = attrs.get('name')
                filename = attrs.get('filename')

        if field_name:
            if filename:
                result[field_name] = {'filename': filename, 'data': body}
            else:
                result[field_name] = body.decode('utf-8', errors='replace').strip()

    return result


def _parse_content_disposition(header_line: str) -> Dict[str, str]:
    """解析 Content-Disposition 头部"""
    attrs = {}
    content = header_line[len('content-disposition:'):].strip()

    in_quote = False
    current_key = ''
    current_value = ''

    for i, char in enumerate(content):
        if char == '"' and (i == 0 or content[i-1] != '\\'):
            in_quote = not in_quote
        elif char == '=' and not in_quote:
            current_key = current_value.strip()
            current_value = ''
        elif char == ';' and not in_quote:
            if current_key:
                attrs[current_key.lower()] = current_value.strip().strip('"')
            current_key = ''
            current_value = ''
        else:
            current_value += char

    if current_key:
        attrs[current_key.lower()] = current_value.strip().strip('"')

    return attrs
