#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片/视频解析工具函数（原生解析，无需第三方库）"""

from typing import Optional, Tuple


def parse_image_size(file_data: bytes, ext: str) -> Tuple[Optional[int], Optional[int]]:
    """从图片数据读取尺寸（原生解析，无需第三方库）

    支持 PNG / JPEG / WebP 格式。

    Args:
        file_data: 图片二进制数据
        ext: 文件扩展名（含点号，如 '.jpg'）

    Returns:
        (width, height) 元组，解析失败返回 (None, None)
    """
    try:
        ext_lower = ext.lower() if ext else ''
        if ext_lower == '.png':
            if len(file_data) >= 24 and file_data[:8] == b'\x89PNG\r\n\x1a\n':
                width = int.from_bytes(file_data[16:20], 'big')
                height = int.from_bytes(file_data[20:24], 'big')
                return width, height
        elif ext_lower in ('.jpg', '.jpeg'):
            if len(file_data) >= 2 and file_data[:2] == b'\xff\xd8':
                idx = 2
                while idx + 4 < len(file_data):
                    if file_data[idx] == 0xff and file_data[idx + 1] == 0xc0:
                        height = int.from_bytes(file_data[idx + 5:idx + 7], 'big')
                        width = int.from_bytes(file_data[idx + 7:idx + 9], 'big')
                        return width, height
                    length = int.from_bytes(file_data[idx + 2:idx + 4], 'big')
                    idx += length + 2
        elif ext_lower == '.webp':
            if len(file_data) >= 20 and file_data[:4] == b'RIFF' and file_data[8:12] == b'WEBP':
                if file_data[12:16] == b'VP8 ':
                    if len(file_data) >= 30:
                        width = int.from_bytes(file_data[26:28], 'little') & 0x3fff
                        height = int.from_bytes(file_data[28:30], 'little') & 0x3fff
                        return width, height
                elif file_data[12:16] == b'VP8L':
                    if len(file_data) >= 21:
                        bits = int.from_bytes(file_data[17:21], 'little')
                        width = ((bits >> 16) & 0x3fff) + 1
                        height = ((bits >> 0) & 0x3fff) + 1
                        return width, height
    except Exception:
        pass
    return None, None


def parse_video_size(file_data: bytes, ext: str) -> Tuple[Optional[int], Optional[int]]:
    """从视频数据读取尺寸（原生解析，无需第三方库）

    支持 MP4/MOV/M4V/3GP（ISO BMFF）、AVI（RIFF）、MKV（EBML）、WMV（ASF）。
    FLV 容器不直接存储宽高，返回 (None, None) 由前端 metadata 兜底。

    Args:
        file_data: 视频二进制数据
        ext: 文件扩展名（含点号，如 '.mp4'）

    Returns:
        (width, height) 元组，解析失败返回 (None, None)
    """
    try:
        ext_lower = ext.lower() if ext else ''
        if ext_lower in ('.mp4', '.mov', '.m4v', '.3gp'):
            return _parse_isobmff_size(file_data)
        elif ext_lower == '.avi':
            return _parse_avi_size(file_data)
        elif ext_lower == '.mkv':
            return _parse_mkv_size(file_data)
        elif ext_lower == '.wmv':
            return _parse_wmv_size(file_data)
    except Exception:
        pass
    return None, None


def _parse_isobmff_size(file_data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """解析 ISO BMFF 容器（MP4/MOV/M4V/3GP）尺寸

    遍历 box 找 tkhd（track header），tkhd data 中 offset 76/80 是 width/height（16.16 fixed point）。
    """
    width = height = None
    idx = 0
    data_len = len(file_data)
    while idx + 8 <= data_len:
        size = int.from_bytes(file_data[idx:idx + 4], 'big')
        box_type = file_data[idx + 4:idx + 8]
        if size == 1:
            # 64 位 size，header 16 字节
            if idx + 16 > data_len:
                break
            size = int.from_bytes(file_data[idx + 8:idx + 16], 'big')
            header_size = 16
        elif size == 0:
            # box 到文件末尾
            size = data_len - idx
            header_size = 8
        else:
            header_size = 8

        if size < 8:
            break

        if box_type == b'tkhd':
            # tkhd data 起始位置
            data_start = idx + header_size
            if data_start + 84 <= data_len:
                w_raw = int.from_bytes(file_data[data_start + 76:data_start + 80], 'big')
                h_raw = int.from_bytes(file_data[data_start + 80:data_start + 84], 'big')
                w = w_raw >> 16
                h = h_raw >> 16
                if w > 0 and h > 0 and w < 65536 and h < 65536:
                    return w, h

        # 递归进入容器 box（moov/trak/mdia/minf/stbl）
        if box_type in (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'udta'):
            inner = _parse_isobmff_size(file_data[idx + header_size:idx + size])
            if inner[0] and inner[1]:
                return inner

        idx += size
    return width, height


def _parse_avi_size(file_data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """解析 AVI（RIFF）尺寸

    扫描 strf chunk，读 BITMAPINFOHEADER 中 biWidth/biHeight（小端）。
    """
    if len(file_data) < 12 or file_data[:4] != b'RIFF' or file_data[8:12] != b'AVI ':
        return None, None

    search_pos = 0
    while True:
        pos = file_data.find(b'strf', search_pos)
        if pos == -1:
            return None, None
        # strf chunk: [strf(4)][size(4)][data...]
        data_start = pos + 8
        if data_start + 12 > len(file_data):
            return None, None
        bi_size = int.from_bytes(file_data[data_start:data_start + 4], 'little')
        if bi_size == 40:
            # 标准 BITMAPINFOHEADER
            width = int.from_bytes(file_data[data_start + 4:data_start + 8], 'little')
            height = int.from_bytes(file_data[data_start + 8:data_start + 12], 'little')
            # biHeight 为正表示 bottom-up，取绝对值
            height = abs(height)
            if 0 < width < 65536 and 0 < height < 65536:
                return width, height
        search_pos = pos + 4


def _parse_mkv_size(file_data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """解析 MKV（EBML）尺寸

    扫描 DisplayWidth（ID 0x54B0）和 DisplayHeight（ID 0x54BA）元素。
    """
    if len(file_data) < 4 or file_data[:4] != b'\x1a\x45\xdf\xa3':
        return None, None

    width = height = None

    # 找 DisplayWidth
    pos_w = file_data.find(b'\x54\xb0')
    if pos_w != -1:
        val = _read_ebml_element_value(file_data, pos_w + 2)
        if val is not None and 0 < val < 65536:
            width = val

    # 找 DisplayHeight
    pos_h = file_data.find(b'\x54\xba')
    if pos_h != -1:
        val = _read_ebml_element_value(file_data, pos_h + 2)
        if val is not None and 0 < val < 65536:
            height = val

    if width and height:
        return width, height
    return None, None


def _read_ebml_element_value(file_data: bytes, value_pos: int) -> Optional[int]:
    """读取 EBML 元素的 size 描述符和后续 data 值

    元素格式: [ID][size VINT][data]
    本函数从 size VINT 起始位置读取，返回 data 的整数值。
    """
    if value_pos >= len(file_data):
        return None
    first_byte = file_data[value_pos]
    # VINT: 前导 1 的个数表示 size 字节数 - 1
    if first_byte & 0x80:
        size_len = 1
    elif first_byte & 0x40:
        size_len = 2
    elif first_byte & 0x20:
        size_len = 3
    elif first_byte & 0x10:
        size_len = 4
    else:
        return None

    # size 值（多字节 VINT）
    mask = (0xFF >> size_len)
    size_value = first_byte & mask
    for i in range(1, size_len):
        if value_pos + i >= len(file_data):
            return None
        size_value = (size_value << 8) | file_data[value_pos + i]
    if size_value == 0 or size_value > 8:
        # 未知 size 或异常长度，跳过
        return None

    data_start = value_pos + size_len
    if data_start + size_value > len(file_data):
        return None
    return int.from_bytes(file_data[data_start:data_start + size_value], 'big')


def _parse_wmv_size(file_data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """解析 WMV（ASF）尺寸

    扫描 BITMAPINFOHEADER（biSize=40 即 \\x28\\x00\\x00\\x00），读 biWidth/biHeight（小端）。
    """
    search_pos = 0
    while True:
        pos = file_data.find(b'\x28\x00\x00\x00', search_pos)
        if pos == -1:
            return None, None
        if pos + 12 <= len(file_data):
            width = int.from_bytes(file_data[pos + 4:pos + 8], 'little')
            height = int.from_bytes(file_data[pos + 8:pos + 12], 'little')
            height = abs(height)
            if 0 < width < 65536 and 0 < height < 65536:
                return width, height
        search_pos = pos + 1
