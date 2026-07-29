#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""授权码工具函数

授权码格式：随机数(8位十六进制) + 到期时间戳(10位) + 类型标识(1位) + 签名(8位十六进制)
最终授权码：'QR-' + Base62(原始字符串的字节)
"""

import hmac
import hashlib
import secrets
import string
import time

from utils.license_config import (
    get_license_secret_key,
    get_license_monthly_days,
    get_license_yearly_days,
)

# Base62 字符集
BASE62_CHARS = string.digits + string.ascii_uppercase + string.ascii_lowercase
BASE62_INDEX = {c: i for i, c in enumerate(BASE62_CHARS)}

# 类型映射
TYPE_TO_CHAR = {
    'monthly': 'M',
    'yearly': 'Y',
    'permanent': 'P',
}
CHAR_TO_TYPE = {v: k for k, v in TYPE_TO_CHAR.items()}

PERMANENT_TS = 9999999999

# 原始字符串固定长度：8 + 10 + 1 + 8 = 27
RAW_LENGTH = 27


def _base62_encode(data: bytes) -> str:
    """Base62 编码字节数组"""
    if not data:
        return ''
    num = int.from_bytes(data, byteorder='big')
    if num == 0:
        return BASE62_CHARS[0]
    chars = []
    while num > 0:
        num, rem = divmod(num, 62)
        chars.append(BASE62_CHARS[rem])
    return ''.join(reversed(chars))


def _base62_decode(s: str) -> bytes:
    """Base62 解码字符串"""
    if not s:
        return b''
    num = 0
    for c in s:
        if c not in BASE62_INDEX:
            raise ValueError('Invalid Base62 character: %r' % c)
        num = num * 62 + BASE62_INDEX[c]
    if num == 0:
        return b'\x00'
    byte_count = (num.bit_length() + 7) // 8
    return num.to_bytes(byte_count, byteorder='big')


def _sign(random_seed: str, expire_ts_str: str, type_char: str) -> str:
    """计算签名（HMAC-SHA256 取前 8 位十六进制）"""
    msg = (random_seed + expire_ts_str + type_char).encode('utf-8')
    secret_key = get_license_secret_key().encode('utf-8')
    sig = hmac.new(secret_key, msg, hashlib.sha256).hexdigest()
    return sig[:8]


def generate_license(code_type: str, expire_ts: int = None) -> str:
    """生成授权码

    :param code_type: 'monthly'/'yearly'/'permanent'
    :param expire_ts: 到期时间戳，None 则自动计算
    :return: 授权码字符串（QR-开头）
    """
    if code_type not in TYPE_TO_CHAR:
        raise ValueError('Invalid code_type: %r' % code_type)

    type_char = TYPE_TO_CHAR[code_type]
    now = int(time.time())

    if expire_ts is None:
        if code_type == 'monthly':
            expire_ts = now + get_license_monthly_days() * 86400
        elif code_type == 'yearly':
            expire_ts = now + get_license_yearly_days() * 86400
        else:  # permanent
            expire_ts = PERMANENT_TS

    expire_ts_str = str(expire_ts).zfill(10)
    if len(expire_ts_str) > 10:
        raise ValueError('expire_ts too large: %r' % expire_ts)

    # 生成 8 位十六进制随机数（4 字节）
    random_seed = secrets.token_hex(4)

    # 计算签名
    signature = _sign(random_seed, expire_ts_str, type_char)

    # 拼接原始字符串
    raw = random_seed + expire_ts_str + type_char + signature
    encoded = _base62_encode(raw.encode('utf-8'))
    return 'QR-' + encoded


def parse_license(code: str) -> dict:
    """解析授权码内容（不校验签名，仅解析内容）

    :param code: 授权码字符串
    :return: {
        'valid_format': bool,
        'code_type': str,
        'expire_time': int,
        'random_seed': str,
        'signature': str,
        'error': str,
    }
    """
    result = {
        'valid_format': False,
        'code_type': '',
        'expire_time': 0,
        'random_seed': '',
        'signature': '',
        'error': '',
    }

    if not isinstance(code, str) or not code.startswith('QR-'):
        result['error'] = '授权码格式不正确，请检查是否完整复制'
        return result

    encoded = code[3:]
    if not encoded:
        result['error'] = '授权码不能为空'
        return result

    try:
        raw_bytes = _base62_decode(encoded)
        raw = raw_bytes.decode('utf-8')
    except Exception:
        result['error'] = '授权码格式不正确，请检查是否完整复制'
        return result

    if len(raw) < RAW_LENGTH:
        result['error'] = '授权码格式不正确，请检查是否完整复制'
        return result

    random_seed = raw[:8]
    expire_ts_str = raw[8:18]
    type_char = raw[18]
    signature = raw[19:27]

    if type_char not in CHAR_TO_TYPE:
        result['error'] = '授权码格式不正确，请检查是否完整复制'
        return result

    try:
        expire_time = int(expire_ts_str)
    except ValueError:
        result['error'] = '授权码格式不正确，请检查是否完整复制'
        return result

    result['valid_format'] = True
    result['code_type'] = CHAR_TO_TYPE[type_char]
    result['expire_time'] = expire_time
    result['random_seed'] = random_seed
    result['signature'] = signature
    return result


def verify_license(code: str) -> dict:
    """校验授权码

    :param code: 授权码字符串
    :return: {
        'valid': bool,
        'code_type': str,
        'expire_time': int,      # 永久卡返回 None
        'error': str,
        'remaining_days': int,   # 永久卡返回 -1
    }
    """
    result = {
        'valid': False,
        'code_type': '',
        'expire_time': None,
        'error': '',
        'remaining_days': 0,
    }

    parsed = parse_license(code)
    if not parsed['valid_format']:
        result['error'] = parsed['error']
        return result

    # 重建原始 expire_ts_str 用于签名校验
    expire_ts_str = str(parsed['expire_time']).zfill(10)
    type_char = TYPE_TO_CHAR[parsed['code_type']]
    expected_sig = _sign(parsed['random_seed'], expire_ts_str, type_char)

    if not hmac.compare_digest(expected_sig, parsed['signature']):
        result['error'] = '授权码无效，请确认从正规渠道获取'
        return result

    result['code_type'] = parsed['code_type']

    # 永久卡
    if parsed['code_type'] == 'permanent':
        result['valid'] = True
        result['expire_time'] = None
        result['remaining_days'] = -1
        return result

    result['expire_time'] = parsed['expire_time']

    # 检查是否过期
    now = int(time.time())
    if now > parsed['expire_time']:
        result['error'] = '授权码已过期，请购买新的授权码'
        return result

    remaining_seconds = parsed['expire_time'] - now
    result['remaining_days'] = max(0, (remaining_seconds + 86399) // 86400)
    result['valid'] = True
    return result
