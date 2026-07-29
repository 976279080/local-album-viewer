#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简单混淆加密工具

用途：让源码中不直接出现敏感默认值（如签名密钥）。
算法：XOR + Base64，非强加密，仅用于源码层面的明文遮蔽。
数据库存储的是解密后的明文（按要求）。
"""

import base64

# 混淆密钥（与默认值分开存放，单独修改不影响已落库的数据）
_OBF_KEY = b'qorder_lic_v1'


def obfuscate(plaintext: str) -> str:
    """加密：明文 -> XOR + Base64 -> 密文字符串"""
    data = plaintext.encode('utf-8')
    encrypted = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode('ascii')


def deobfuscate(ciphertext: str) -> str:
    """解密：obfuscate() 的逆操作"""
    encrypted = base64.b64decode(ciphertext)
    data = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(encrypted))
    return data.decode('utf-8')
