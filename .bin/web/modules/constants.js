/**
 * 前端常量模块 - 集中管理散落在 app.js 中的常量
 * 遵循单一职责原则：仅负责常量定义
 * 依赖：config.js（window.APP_CONFIG）
 */
(function () {
    'use strict';

    const config = window.APP_CONFIG || {};

    // 评分等级
    const RATING_LEVELS = config.rating?.levels ?? [
        { val: 2, label: '很喜欢' },
        { val: 1, label: '有点喜欢' },
        { val: 0, label: '正常' },
        { val: -1, label: '不喜欢' }
    ];

    // 非法字符
    const ILLEGAL_CHARS_STR = config.validation?.illegalChars ?? '\\/:*?"<>|.';
    const COMMENT_ILLEGAL_CHARS_STR = config.validation?.commentIllegalChars ?? '\\/:*?"<>|';

    // 文件类型
    const VIDEO_EXTENSIONS = config.fileTypes?.videoExtensions ??
        ['mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'm4v', '3gp'];

    // 标签颜色（hash 后取色）
    const TAG_COLORS = ['#4ecdc4', '#45b7d1', '#96ceb4', '#ff6b6b', '#feca57', '#ff9ff3', '#54a0ff', '#5f27cd'];

    // 心形SVG（按评分等级）- 圆润对称版本
    const HEART_PATH = "M 0,-75 C -8,-105 -30,-128 -65,-128 C -105,-128 -148,-98 -148,-55 C -148,-15 -118,20 -85,50 C -55,78 -25,108 0,135 C 25,108 55,78 85,50 C 118,20 148,-15 148,-55 C 148,-98 105,-128 65,-128 C 30,-128 8,-105 0,-75 Z";
    const HEART_PATH_LEFT = "M 0,-75 C -8,-105 -30,-128 -65,-128 C -105,-128 -148,-98 -148,-55 C -148,-15 -118,20 -85,50 C -55,78 -25,108 0,135 Z";
    const HEART_PATH_RIGHT = "M 0,-75 C 8,-105 30,-128 65,-128 C 105,-128 148,-98 148,-55 C 148,-15 118,20 85,50 C 55,78 25,108 0,135 Z";
    const HEART_SVG = {
        full: `<svg viewBox="-160 -160 320 320" width="24" height="24"><path d="${HEART_PATH}" fill="#ff5252"/></svg>`,
        half: `<svg viewBox="-160 -160 320 320" width="24" height="24"><path d="${HEART_PATH_LEFT}" fill="#ff5252"/><path d="${HEART_PATH_RIGHT}" fill="#e8e8e8"/></svg>`,
        empty: `<svg viewBox="-160 -160 320 320" width="24" height="24"><path d="${HEART_PATH}" fill="#e8e8e8"/></svg>`,
        broken: `<svg viewBox="-160 -160 320 320" width="24" height="24"><path d="${HEART_PATH}" fill="#b9bcbf"/><path d="M -10,-95 L 18,-30 L -18,30 L 15,85" stroke="#808386" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    };

    // 根据评分获取心形SVG
    const getHeartSvg = (rating) => {
        const r = rating || 0;
        if (r >= 2) return HEART_SVG.full;
        if (r === 1) return HEART_SVG.half;
        if (r === 0) return HEART_SVG.empty;
        return HEART_SVG.broken;
    };

    // UI
    const NOTIFICATION_DURATION = config.ui?.notificationDurationMs ?? 2500;

    // 分批渲染
    const INITIAL_RENDER_COUNT = config.render?.initialCount ?? 300;
    const RENDER_BATCH_SIZE = config.render?.batchSize ?? 200;

    // 认证
    const PASSWORD_STORAGE_KEY = config.auth?.passwordStorageKey ?? 'password';

    // 重试
    const RETRY_SUMMARY = config.retry?.summaryRetries ?? 10;
    const RETRY_HOME_INIT = config.retry?.homeInitRetries ?? 15;
    const RETRY_INTERVAL = config.retry?.intervalMs ?? 200;

    // API 路径
    const API = {
        summary: config.api?.summary ?? '/api/summary',
        homeInit: config.api?.homeInit ?? '/api/home-init',
        albumInit: config.api?.albumInit ?? '/api/album-init',
        photo: config.api?.photo ?? '/api/photo',
        update: config.api?.update ?? '/api/update',
        comment: config.api?.comment ?? '/api/comments',
        commentAdd: config.api?.commentAdd ?? '/api/comments/add',
        commentDelete: config.api?.commentDelete ?? '/api/comments/delete',
        delete: config.api?.delete ?? '/api/delete',
        batchTag: config.api?.batchTag ?? '/api/batch-tag',
        batchDelete: config.api?.batchDelete ?? '/api/batch-delete',
        batchClearTags: config.api?.batchClearTags ?? '/api/batch-clear-tags',
        verify: config.api?.verify ?? '/api/verify'
    };

    // 预编译正则（转义字符串中的每个字符）
    const escapeRegex = (s) => s.replace(/(.)/g, '\\$1');
    const ILLEGAL_CHARS = new RegExp('[' + escapeRegex(ILLEGAL_CHARS_STR) + ']');
    const COMMENT_ILLEGAL_CHARS = new RegExp('[' + escapeRegex(COMMENT_ILLEGAL_CHARS_STR) + ']');

    window.AppConstants = {
        RATING_LEVELS,
        ILLEGAL_CHARS_STR, ILLEGAL_CHARS,
        COMMENT_ILLEGAL_CHARS_STR, COMMENT_ILLEGAL_CHARS,
        VIDEO_EXTENSIONS, TAG_COLORS,
        HEART_SVG, getHeartSvg,
        NOTIFICATION_DURATION,
        INITIAL_RENDER_COUNT, RENDER_BATCH_SIZE,
        PASSWORD_STORAGE_KEY,
        RETRY_SUMMARY, RETRY_HOME_INIT, RETRY_INTERVAL,
        API
    };
})();
