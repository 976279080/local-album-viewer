/**
 * 前端 API 封装模块 - 统一管理所有 HTTP 请求
 * 遵循单一职责原则：仅负责请求发送与响应解析，不持有业务状态
 * 依赖：constants.js（window.AppConstants）
 */
(function () {
    'use strict';

    const C = window.AppConstants;

    /** 从 sessionStorage 读取密码 */
    function getPassword() {
        return sessionStorage.getItem(C.PASSWORD_STORAGE_KEY) || '';
    }

    function setPassword(pwd) {
        if (pwd) sessionStorage.setItem(C.PASSWORD_STORAGE_KEY, pwd);
    }

    function clearPassword() {
        sessionStorage.removeItem(C.PASSWORD_STORAGE_KEY);
    }

    /** 带 X-Auth 的 fetch（自动注入密码） */
    function authFetch(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-Auth': getPassword(),
            ...options.headers
        };
        return fetch(url, { ...options, headers });
    }

    /**
     * 统一 POST 请求（可选鉴权）
     * @param {string} url 接口地址
     * @param {object} body 请求体
     * @param {string} [password] 密码（不传则不带 X-Auth）
     * @returns {Promise<{ok, status, data}>}
     */
    async function authPost(url, body, password) {
        const headers = { 'Content-Type': 'application/json' };
        if (password) headers['X-Auth'] = password;
        const r = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        });
        let data = null;
        try { data = await r.json(); } catch (e) { /* 忽略解析失败 */ }
        return { ok: r.ok, status: r.status, data };
    }

    /** 是否 401 未授权 */
    function isUnauthorized(result) {
        return result.status === 401;
    }

    window.AppApi = {
        getPassword, setPassword, clearPassword,
        authFetch, authPost,
        isUnauthorized,
        // 便捷接口
        fetchSummary: () => fetch(C.API.summary).then(r => r.json()),
        fetchHomeInit: (albumParam) => {
            const url = albumParam
                ? `${C.API.homeInit}?album=${encodeURIComponent(albumParam)}`
                : C.API.homeInit;
            return fetch(url).then(r => r.json());
        },
        fetchAlbumInit: (album, year) => {
            let url = `${C.API.albumInit}?album=${encodeURIComponent(album)}`;
            if (year !== undefined && year !== null) url += `&year=${encodeURIComponent(year)}`;
            return fetch(url).then(r => r.json());
        },
        fetchPhotoDetail: (id) => authFetch(`${C.API.photo}?id=${id}`).then(r => r.json()),
        updatePhoto: (body, password) => authPost(C.API.update, body, password),
        deletePhoto: (pathKey, password) => authPost(C.API.delete, { path_key: pathKey }, password),
        addComment: (photoId, text) => authPost(C.API.commentAdd, { photo_id: photoId, text: text }),
        deleteComment: (commentId, password) => authPost(C.API.commentDelete, { comment_id: commentId }, password),
        batchTag: (pathKeys, tags, password) => authPost(C.API.batchTag, { path_keys: pathKeys, tags: tags }, password),
        batchDelete: (pathKeys, password) => authPost(C.API.batchDelete, { path_keys: pathKeys }, password),
        batchClearTags: (pathKeys, password) => authPost(C.API.batchClearTags, { path_keys: pathKeys }, password),
        verifyPassword: (password) => fetch(C.API.verify, {
            method: 'POST',
            headers: { 'X-Auth': password || '' }
        }).then(r => r.ok).catch(() => false)
    };
})();
