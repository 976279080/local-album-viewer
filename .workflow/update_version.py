#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 流水线中更新 version.json 并 push 回仓库

读取环境变量 GITEE_TAG（如 v0.0.4），更新 version.json 的 latest_version
和 versions 数组，然后 git commit + push 回 main 分支。

需在 Gitee Go 流水线设置中配置 GITEE_TOKEN 环境变量
（Personal Access Token，需 projects 权限用于 push）。
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

# 仓库标识（从 GITEE_RAW_BASE 提取）
OWNER_REPO = 'cdgm/local-album-viewer'

# 项目根目录：.workflow/update_version.py → 上两级
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / 'version.json'


def main():
    tag = os.environ.get('GITEE_TAG', '').strip()
    if not tag:
        print('GITEE_TAG 环境变量为空，跳过 version.json 更新')
        return

    # v0.0.4 → 0.0.4
    version = tag[1:] if tag.startswith('v') else tag
    # Gitee Release 附件稳定 URL
    download_url = f'https://gitee.com/{OWNER_REPO}/releases/download/{tag}/.bin.zip'

    # 读取现有 version.json
    if VERSION_FILE.exists():
        data = json.loads(VERSION_FILE.read_text(encoding='utf-8'))
    else:
        data = {'latest_version': '', 'versions': []}
    data.setdefault('versions', [])

    # 更新 latest_version
    data['latest_version'] = version

    # 已存在则更新，否则头部插入
    entry = {
        'version': version,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'changelog': '',
        'download_url': download_url,
    }
    existing = [v for v in data['versions'] if str(v.get('version', '')).strip() == version]
    if existing:
        existing[0].update(entry)
    else:
        data['versions'].insert(0, entry)

    VERSION_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'已更新 version.json: latest_version={version}, download_url={download_url}')

    # git push 回 main
    token = os.environ.get('GITEE_TOKEN', '').strip()
    if not token:
        print('GITEE_TOKEN 未配置，跳过 push（version.json 仅在 CI 工作区修改）')
        return

    _git(['config', 'user.email', 'ci@gitee.local'])
    _git(['config', 'user.name', 'Gitee CI'])
    _git(['add', 'version.json'])
    _git(['commit', '-m', f'ci: 更新 version.json 到 {version}'])
    # 用 token 认证 push 到 main
    remote = f'https://x-access-token:{token}@gitee.com/{OWNER_REPO}.git'
    _git(['push', remote, 'HEAD:main'])
    print('version.json 已 push 回 main')


def _git(args, check=True):
    """在项目根目录执行 git 命令"""
    result = subprocess.run(['git'] + args, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=__import__('sys').stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f'git {args[0]} 失败: {result.stderr}')
    return result


if __name__ == '__main__':
    main()
