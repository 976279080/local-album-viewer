#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP4 Fast Start 工具 - 将 moov atom 移到文件开头，支持流式播放与进度条拖拽
无需 ffmpeg，纯 Python 实现，仅处理 mp4 容器结构
"""

import struct
from pathlib import Path
from typing import Optional


class MP4Atom:
    """MP4 atom 基础结构"""

    def __init__(self, offset: int, size: int, atype: str, header_size: int = 8):
        self.offset = offset
        self.size = size
        self.type = atype
        self.header_size = header_size

    @property
    def data_offset(self) -> int:
        return self.offset + self.header_size

    @property
    def data_size(self) -> int:
        return self.size - self.header_size


def read_atom_header(f, offset: int) -> Optional[MP4Atom]:
    """读取 atom 头部信息"""
    f.seek(offset)
    header = f.read(8)
    if len(header) < 8:
        return None

    size = struct.unpack('>I', header[:4])[0]
    atype = header[4:8].decode('ascii', errors='replace')
    header_size = 8

    if size == 1:
        ext_header = f.read(8)
        if len(ext_header) < 8:
            return None
        size = struct.unpack('>Q', ext_header)[0]
        header_size = 16
    elif size == 0:
        f.seek(0, 2)
        size = f.tell() - offset

    return MP4Atom(offset, size, atype, header_size)


def find_atom(f, parent_offset: int, parent_size: int, atom_type: str) -> Optional[MP4Atom]:
    """在父 atom 中查找指定类型的子 atom"""
    pos = parent_offset + 8
    end = parent_offset + parent_size
    while pos < end:
        atom = read_atom_header(f, pos)
        if not atom:
            break
        if atom.type == atom_type:
            return atom
        pos += atom.size
    return None


def get_child_atoms(f, parent: MP4Atom) -> list:
    """获取父 atom 的所有子 atom"""
    children = []
    pos = parent.data_offset
    end = parent.offset + parent.size
    while pos < end:
        atom = read_atom_header(f, pos)
        if not atom:
            break
        children.append(atom)
        pos += atom.size
    return children


def _rewrite_stco_chunk_offsets(f, moov_atom: MP4Atom, mdat_offset_delta: int) -> None:
    """重写 stco（chunk offset）box 中的偏移量"""
    moov_data_start = moov_atom.data_offset
    moov_data_end = moov_atom.offset + moov_atom.size

    def process_atom(offset, size):
        pos = offset
        end = offset + size
        while pos < end:
            atom = read_atom_header(f, pos)
            if not atom:
                break
            if atom.type == 'stco':
                # stco 结构: 4字节 version+flags, 4字节 entry_count, N*4字节 entries
                f.seek(atom.data_offset + 4)  # 跳过 version+flags
                entry_count = struct.unpack('>I', f.read(4))[0]
                for i in range(entry_count):
                    entry_pos = atom.data_offset + 8 + i * 4  # 8 = version+flags(4) + entry_count(4)
                    f.seek(entry_pos)
                    old_offset = struct.unpack('>I', f.read(4))[0]
                    new_offset = old_offset + mdat_offset_delta
                    f.seek(entry_pos)
                    f.write(struct.pack('>I', new_offset))
            elif atom.type == 'co64':
                # co64 结构: 4字节 version+flags, 4字节 entry_count, N*8字节 entries
                f.seek(atom.data_offset + 4)  # 跳过 version+flags
                entry_count = struct.unpack('>I', f.read(4))[0]
                for i in range(entry_count):
                    entry_pos = atom.data_offset + 8 + i * 8
                    f.seek(entry_pos)
                    old_offset = struct.unpack('>Q', f.read(8))[0]
                    new_offset = old_offset + mdat_offset_delta
                    f.seek(entry_pos)
                    f.write(struct.pack('>Q', new_offset))
            else:
                if atom.type in ('trak', 'mdia', 'minf', 'stbl', 'moov'):
                    process_atom(atom.data_offset, atom.data_size)
            pos += atom.size

    process_atom(moov_data_start, moov_atom.data_size)


def make_fast_start(input_path: Path, output_path: Path) -> bool:
    """
    将 mp4 文件转换为 fast start 格式（moov atom 移到 mdat 前面）
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
    
    Returns:
        True 表示成功转换，False 表示不需要转换或转换失败
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    file_size = input_path.stat().st_size
    if file_size < 16:
        return False

    top_atoms = []
    with open(input_path, 'rb') as f:
        pos = 0
        while pos < file_size:
            atom = read_atom_header(f, pos)
            if not atom:
                break
            top_atoms.append(atom)
            pos += atom.size

    mdat_atom = None
    moov_atom = None
    for atom in top_atoms:
        if atom.type == 'mdat':
            mdat_atom = atom
        elif atom.type == 'moov':
            moov_atom = atom

    if not mdat_atom or not moov_atom:
        return False

    if moov_atom.offset < mdat_atom.offset:
        return False

    ftyp_atoms = [a for a in top_atoms if a.type in ('ftyp', 'free') and a.offset < mdat_atom.offset]

    other_atoms = [
        a for a in top_atoms
        if a.type not in ('ftyp', 'free', 'mdat', 'moov')
    ]

    with open(input_path, 'rb') as fin:
        with open(output_path, 'wb') as fout:
            for atom in ftyp_atoms:
                fin.seek(atom.offset)
                fout.write(fin.read(atom.size))

            fin.seek(moov_atom.offset)
            moov_data = fin.read(moov_atom.size)
            moov_start = fout.tell()
            fout.write(moov_data)

            mdat_start = fout.tell()
            fin.seek(mdat_atom.offset)
            fout.write(fin.read(mdat_atom.size))

            for atom in other_atoms:
                fin.seek(atom.offset)
                fout.write(fin.read(atom.size))

    mdat_offset_delta = mdat_start - mdat_atom.offset

    with open(output_path, 'r+b') as f:
        new_moov_atom = read_atom_header(f, moov_start)
        if new_moov_atom:
            _rewrite_stco_chunk_offsets(f, new_moov_atom, mdat_offset_delta)

    return True


def is_fast_start(file_path: Path) -> bool:
    """检查 mp4 文件是否已经是 fast start 格式（moov 在 mdat 前面）"""
    file_path = Path(file_path)
    file_size = file_path.stat().st_size
    if file_size < 16:
        return True

    mdat_offset = None
    moov_offset = None

    with open(file_path, 'rb') as f:
        pos = 0
        while pos < file_size:
            atom = read_atom_header(f, pos)
            if not atom:
                break
            if atom.type == 'mdat':
                mdat_offset = pos
            elif atom.type == 'moov':
                moov_offset = pos
                break
            pos += atom.size

    if mdat_offset is None or moov_offset is None:
        return True

    return moov_offset < mdat_offset
