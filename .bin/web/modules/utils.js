/**
 * 前端工具函数模块 - 纯函数集合
 * 遵循单一职责原则：仅提供无状态、无副作用的工具函数
 * 依赖：constants.js（window.AppConstants）
 */
(function () {
    'use strict';

    const C = window.AppConstants;

    /** 判断文件名是否为视频 */
    function isVideo(filename) {
        if (!filename || typeof filename !== 'string') return false;
        const ext = filename.split('.').pop().toLowerCase();
        return C.VIDEO_EXTENSIONS.includes(ext);
    }

    /** 将时间戳/日期字符串解析为 Date 对象，无效返回 null */
    function parseTimestamp(dateStr) {
        if (!dateStr || dateStr === '-') return null;
        let ts = dateStr;
        if (typeof dateStr === 'number' || (!isNaN(dateStr) && !String(dateStr).includes('-'))) {
            ts = parseInt(dateStr, 10) * 1000;
        }
        const d = new Date(ts);
        return isNaN(d.getTime()) ? null : d;
    }

    /** 格式化日期为 M-D（不含前导零） */
    function formatDate(dateStr) {
        const d = parseTimestamp(dateStr);
        if (!d) return '';
        return `${d.getMonth() + 1}-${d.getDate()}`;
    }

    /** 格式化日期时间为 YYYY-MM-DD HH:MM */
    function formatDateTime(dateStr, expectedYear) {
        const d = parseTimestamp(dateStr);
        if (!d) return '';
        const year = expectedYear !== undefined ? expectedYear : d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}`;
    }

    /** 格式化评论日期为 YYYY-M-D（不含前导零） */
    function formatCommentDate(dateStr) {
        const d = parseTimestamp(dateStr);
        if (!d) return '';
        return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    }

    /** 判断 update_time 是否为当日 */
    function isModifiedToday(updateTime) {
        const d = parseTimestamp(updateTime);
        if (!d) return false;
        const now = new Date();
        return d.getFullYear() === now.getFullYear()
            && d.getMonth() === now.getMonth()
            && d.getDate() === now.getDate();
    }

    /** 格式化文件大小 */
    function formatFileSize(bytes) {
        if (!bytes) return '-';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    /** 根据标签名 hash 取颜色 */
    function getRandomTagColor(tag) {
        if (!tag) return C.TAG_COLORS[0];
        let hash = 0;
        for (let i = 0; i < tag.length; i++) {
            hash = tag.charCodeAt(i) + ((hash << 5) - hash);
        }
        return C.TAG_COLORS[Math.abs(hash) % C.TAG_COLORS.length];
    }

    /** 编码 path_key（按 / 分段 encodeURIComponent） */
    function encodePathKey(pathKey) {
        if (!pathKey) return '';
        const parts = pathKey.split('/');
        return parts.map(p => encodeURIComponent(p)).join('/');
    }

    /** 判断两个数组作为集合是否相等（无视顺序、去重） */
    function arraysSameAsSet(a, b) {
        const arr1 = Array.isArray(a) ? a : [];
        const arr2 = Array.isArray(b) ? b : [];
        if (arr1.length !== arr2.length) return false;
        const set1 = new Set(arr1);
        for (const item of arr2) {
            if (!set1.has(item)) return false;
        }
        return true;
    }

    /** 文本是否包含非法字符 */
    function hasIllegalChars(text) {
        return !!text && C.ILLEGAL_CHARS.test(text);
    }

    /** 评论文本是否包含非法字符 */
    function hasCommentIllegalChars(text) {
        return !!text && C.COMMENT_ILLEGAL_CHARS.test(text);
    }

    /** 图片加载失败占位图 */
    function handleImageError(e) {
        const img = e.target;
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 200 200"%3E%3Crect fill="%23f0f0f0" width="200" height="200"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dominant-baseline="middle" fill="%23999" font-family="sans-serif" font-size="14"%3E%E5%9B%BE%E7%89%87%E5%8A%A0%E8%BD%BD%E5%A4%B1%E8%B4%A5%3C/text%3E%3C/svg%3E';
    }

    function handleImageLoad(e) {
        e.target.classList.add('loaded');
    }

    /** 视频缩略图加载失败占位 */
    function handleVideoThumbnailError(e) {
        const img = e.target;
        img.style.display = 'none';
        const container = img.parentElement;
        const placeholder = document.createElement('div');
        placeholder.className = 'video-placeholder';
        placeholder.textContent = '🎬';
        container.appendChild(placeholder);
    }

    window.AppUtils = {
        isVideo, parseTimestamp, formatDate, formatDateTime, formatCommentDate,
        isModifiedToday, formatFileSize, getRandomTagColor, encodePathKey,
        arraysSameAsSet, hasIllegalChars, hasCommentIllegalChars,
        handleImageError, handleImageLoad, handleVideoThumbnailError
    };
})();
