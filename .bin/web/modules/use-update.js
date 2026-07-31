/**
 * useUpdate —— 前端版本更新解耦模块
 * 
 * 单一职责：一切和「更新」相关的 UI / HTTP 调用，全部收拢在这里，和 upload.js 主业务解耦。
 * 对外仅暴露 3 个入口 + 1 个调试对象：
 *   - bindButtons(root)      绑定按钮点击事件（update.js 只需要在 init 里调用一次）
 *   - initAutoCheck()        页面加载后自动检查一次更新（如有更新在按钮上加红点）
 *   - forceCheckUpdate()     手动执行「检查更新」（用于按钮 onclick）
 *   - _debug                 调试用：直接访问内部方法
 * 
 * 依赖（由外部注入，保持模块独立不依赖 upload.js 的闭包）：
 *   - {showToast, getPassword, clearPassword, escapeHtml}
 *   - Api 对象（Api.getPassword / Api.setPassword 等可选）
 *   - API_SUMMARY 常量（默认 '/api/summary'）
 */
(function (global) {
    'use strict';

    // —— 模块内部依赖，init 时注入 ——
    var _deps = {
        showToast: function (msg, type) { try { global.alert(msg); } catch (_) {} },
        getPassword: function () { return Promise.resolve(''); },
        clearPassword: function () {},
        escapeHtml: function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]);
        }); },
        API_SUMMARY: '/api/summary',
    };

    // —— 内部方法：1) checkUpdate  2) showVersionModal  3) doDownloadUpdate
    //           4) showRestartCountdownModal  5) safeReload —— 
    async function checkUpdate() {
        var btn = document.getElementById('checkUpdateBtn');
        if (!btn) return;
        var originalDisabled = btn.disabled;
        var originalTextEl = btn.querySelector('.update-btn-text');
        if (!originalTextEl) {
            // 按钮内容没包一层 <span class="update-btn-text">，做一次简单的兼容：将文字包裹一下，避免
            // finally 恢复 btn.innerHTML 时把 #updateBadge 的状态也覆盖掉。
            var cloneBadge = document.getElementById('updateBadge');
            var badgeHtml = cloneBadge ? cloneBadge.outerHTML : '';
            // 提取文字（不含红点）并重新写入，使得以后 btn.firstChild 或 .update-btn-text 能访问
            var txt = (btn.textContent || '检查更新').replace(/[●○]/g, '').trim() || '检查更新';
            btn.innerHTML = '<span class="update-btn-text">' + txt + '</span> ' + badgeHtml;
            originalTextEl = btn.querySelector('.update-btn-text');
        }
        var loadingHtml =
            '加载中...';
        btn.disabled = true;
        if (originalTextEl) originalTextEl.innerHTML = loadingHtml;

        try {
            var res = await fetch('/api/version/list');
            var data = await res.json();
            if (data.error) {
                _deps.showToast('获取版本信息失败，请确认网络正常', 'error');
                return;
            }
            // 手动检查 = 用户已经看到版本信息了，本次生命周期不要再亮红点（防止 initAutoCheck 晚回来覆盖）
            _snoozeUpdateDot();
            showVersionModal(data);
        } catch (e) {
            _deps.showToast('检查更新失败，请确认网络正常', 'error');
        } finally {
            btn.disabled = originalDisabled;
            if (originalTextEl) originalTextEl.textContent = '检查更新';
            // Snooze 之后红点不能再亮；其它情况保持当前状态即可，不再额外修改
            if (_updateDotSnoozed) _setUpdateDot(false);
        }
    }

    // —— 内部 Helper：红点管理（需求1：小红点 = 稳定版最新比本地高） ——
    // 用户一旦手动点过「检查更新」或打开过版本弹窗，本次页面生命周期内自动检查就不再亮起红点，
    // 避免和 showVersionModal 里主动「清红点」的逻辑产生竞态（initAutoCheck 异步返回后把红点又覆盖开）。
    var _updateDotSnoozed = false;
    function _getBadgeEl() {
        return document.getElementById('updateBadge');
    }
    function _snoozeUpdateDot() { _updateDotSnoozed = true; }
    function _setUpdateDot(show) {
        // show=true 时如果已经打了 snooze 标记，就不要再亮红点（防止异步覆盖用户操作）
        if (show && _updateDotSnoozed) return;
        // 新 HTML：优先操作 upload.html 里的静态 <span id="updateBadge">
        var badge = _getBadgeEl();
        if (badge) {
            badge.style.display = show ? '' : 'none';
            return;
        }
        // fallback：没 id=updateBadge 的旧页面，用字符串替换插进 innerHTML
        var btn = document.getElementById('checkUpdateBtn');
        if (!btn) return;
        if (show) {
            if (btn.innerHTML.indexOf('●') === -1) {
                btn.innerHTML = (btn.innerHTML || '检查更新').replace(/检查更新/, '检查更新 <span style="color:#ef4444;">●</span>');
            }
        } else {
            btn.innerHTML = (btn.innerHTML || '检查更新').replace(/\s*<span[^>]*>●<\/span>/g, '');
        }
    }

    function showVersionModal(data) {
        var existing = document.getElementById('versionModal');
        if (existing) existing.remove();

        var localVersion = data.local_version || '未知';
        var versions = data.versions || [];
        var latestVersion = data.latest_version || '';
        var latestStableVersion = data.latest_stable_version || latestVersion || '';
        var esc = _deps.escapeHtml;

        var versionsHtml = '';
        if (versions.length === 0) {
            versionsHtml = '<div class="version-empty">暂无版本信息</div>';
        } else {
            versionsHtml = versions.map(function (v, idx) {
                var isCurrent = v.version === localVersion;
                var isStable = v.is_stable !== false;   // 缺省视为 true（后端老版本可能没带字段）
                var changelog = v.changelog || '暂无更新说明';
                var changelogHtml = changelog
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/### (.+)/g, '<strong>$1</strong>')
                    .replace(/^- (.+)$/gm, '<div class="changelog-item">• $1</div>');
                var actionHtml = '';
                if (isCurrent) {
                    actionHtml = '<span class="version-current-tag">当前版本</span>';
                } else if (!isStable) {
                    // 需求2：只有稳定版才能更新，非稳定版按钮禁用并提示
                    actionHtml =
                        '<button class="version-update-btn" disabled title="非稳定版，暂不开放更新" style="opacity:0.45;cursor:not-allowed;">' +
                        '仅限稳定版更新' +
                        '</button>';
                } else if (v.download_url) {
                    actionHtml =
                        '<button class="version-update-btn" ' +
                        'data-url="' + esc(v.download_url) + '" ' +
                        'data-version="' + esc(v.version) + '"' +
                        '>更新到此版本</button>';
                } else {
                    actionHtml = '<span class="version-no-download">暂无下载地址</span>';
                }
                // 非稳定版标签角标
                var tagHtml = '';
                if (!isStable) {
                    tagHtml = '<span class="version-tag-unstable" style="display:inline-block;margin-left:6px;padding:1px 8px;font-size:11px;border-radius:10px;background:#fef3c7;color:#92400e;border:1px solid #fcd34d;vertical-align:middle;">测试版</span>';
                }
                var itemId = 'v-changelog-' + idx;
                return (
                    '<div class="version-item' + (isCurrent ? ' current' : '') + '">' +
                        '<div class="version-item-header">' +
                            '<span class="version-number">v' + esc(v.version) + '</span>' +
                            tagHtml +
                            '<span class="version-date">' + esc(v.date || '') + '</span>' +
                            actionHtml +
                        '</div>' +
                        // 需求3：更新说明最多 2 行，超出折叠 + 展开/收起
                        '<div class="changelog-wrap" style="margin-top:8px;">' +
                            '<div id="' + itemId + '" class="changelog-text version-changelog" style="display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;line-height:1.6;">' +
                                changelogHtml +
                            '</div>' +
                            '<button class="changelog-toggle" data-for="' + itemId + '" style="display:none;margin-top:4px;padding:2px 0;border:0;background:none;color:#3b82f6;font-size:12px;cursor:pointer;">显示更多</button>' +
                        '</div>' +
                    '</div>'
                );
            }).join('');
        }

        var hasUpdate = latestStableVersion && latestStableVersion !== localVersion;

        var modal = document.createElement('div');
        modal.className = 'version-modal';
        modal.id = 'versionModal';
        modal.innerHTML =
            '<div class="version-modal-mask"></div>' +
            '<div class="version-modal-content">' +
                '<div class="version-modal-header">' +
                    '<h3>版本更新</h3>' +
                    '<button class="version-modal-close">&times;</button>' +
                '</div>' +
                '<div class="version-modal-current">' +
                    '当前版本：<span class="version-current-badge">v' + esc(localVersion) + '</span>' +
                    (hasUpdate ? '<span class="version-new-badge">有新版本 v' + esc(latestStableVersion) + '</span>' : '<span class="version-latest-badge">已是最新</span>') +
                '</div>' +
                '<div class="version-modal-list">' + versionsHtml + '</div>' +
            '</div>';

        document.body.appendChild(modal);

        modal.querySelector('.version-modal-mask').onclick = function () { modal.remove(); };
        modal.querySelector('.version-modal-close').onclick = function () { modal.remove(); };

        // 需求3：每个 changelog 是否真的超过 2 行，超过才显示「显示更多」按钮
        var toggles = modal.querySelectorAll('.changelog-toggle');
        for (var ti = 0; ti < toggles.length; ti++) {
            (function (btn) {
                var forId = btn.getAttribute('data-for');
                var el = forId ? document.getElementById(forId) : null;
                if (!el) return;
                if (el.scrollHeight > el.clientHeight + 1) {
                    btn.style.display = '';
                }
                btn.onclick = function () {
                    var expanded = el.getAttribute('data-expanded') === '1';
                    if (expanded) {
                        // 收起：恢复 line-clamp 2 行
                        el.style.display = '-webkit-box';
                        el.style.webkitBoxOrient = 'vertical';
                        el.style.webkitLineClamp = '2';
                        el.style.overflow = 'hidden';
                        el.setAttribute('data-expanded', '0');
                        btn.textContent = '显示更多';
                    } else {
                        // 展开：移除 line-clamp
                        el.style.display = '';
                        el.style.webkitBoxOrient = '';
                        el.style.webkitLineClamp = '';
                        el.style.overflow = '';
                        el.setAttribute('data-expanded', '1');
                        btn.textContent = '收起';
                    }
                };
            })(toggles[ti]);
        }

        // 需求1：用户已手动打开版本弹窗 -> 清掉红点（不管更不更新），并打 snooze 标记防止 initAutoCheck 覆盖
        _snoozeUpdateDot();
        _setUpdateDot(false);

        var updateBtns = modal.querySelectorAll('.version-update-btn');
        for (var i = 0; i < updateBtns.length; i++) {
            updateBtns[i].onclick = doDownloadUpdate;
        }
    }

    /**
     * 主流程：下载 → trigger-restart → 倒计时进度环 → 探活 reload
     */
    async function doDownloadUpdate(ev) {
        var btn = ev && ev.currentTarget;
        var url = btn ? btn.getAttribute('data-url') || '' : '';
        var version = btn ? btn.getAttribute('data-version') || '' : '';
        if (!url) return;

        // 1) 获取密码
        var pwd = await _deps.getPassword();
        if (!pwd) return;

        // 2) 按钮 loading
        var btns = document.querySelectorAll('#versionModal .version-update-btn');
        var originalText = btn ? btn.textContent : '';
        btns.forEach(function (b) { b.disabled = true; });
        if (btn) btn.textContent = '下载中...';

        try {
            var res = await fetch('/api/version/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Auth': pwd },
                body: JSON.stringify({ download_url: url, version: version }),
            });
            var payload = null;
            try { payload = await res.json(); } catch (_) {}

            if (res.status === 401) {
                _deps.clearPassword();
                _deps.showToast('密码错误，无法执行更新', 'error');
                return;
            }
            if (!payload) {
                _deps.showToast('更新失败：服务端无响应', 'error');
                return;
            }

            var restartRequired = !!payload.restart_required;
            if (!payload.success) {
                if (!restartRequired) {
                    _deps.showToast(payload.message || '更新失败', 'error');
                    return;
                }
            }

            // → trigger-restart：后端先回 HTTP 响应，再 fork restarter 终止父进程
            var restartRes = await fetch('/api/version/trigger-restart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Auth': pwd },
                body: JSON.stringify({ port: location.port ? parseInt(location.port, 10) : 8089 }),
            }).catch(function () { return null; });

            var restartPayload = null;
            if (restartRes && restartRes.ok) {
                try { restartPayload = await restartRes.json(); } catch (_) {}
            }

            // 一律走「倒计时进度环 + 自动 reload」——即使 trigger-restart 接口暂时失败（比如
            // 父进程已在 kill 过程中导致 fetch 报错），也会持续探活，服务恢复后自动 reload
            // （完全移除 showDownloadSuccessModal fallback，不允许出现"请关闭浏览器双击启动"）
            showRestartCountdownModal({
                estimatedMs: (restartPayload && restartPayload.restart_in_ms) ? restartPayload.restart_in_ms + 18000 : 20000,
                port: location.port ? parseInt(location.port, 10) : 8089,
                restartPayload: restartPayload,
                prepareMsg: payload.message || '更新包已准备完成，正在重启...',
            });
        } catch (e) {
            _deps.showToast('更新失败：' + (e && e.message ? e.message : '网络错误'), 'error');
        } finally {
            btns.forEach(function (b) { b.disabled = false; });
            if (btn) btn.textContent = originalText;
        }
    }

    function showRestartCountdownModal(opts) {
        opts = opts || {};
        var esc = _deps.escapeHtml;
        var estimatedMs = Math.max(8000, parseInt(opts.estimatedMs, 10) || 20000);
        var port = opts.port || 8089;
        var vmodal = document.getElementById('versionModal');
        if (vmodal) vmodal.remove();
        var old = document.getElementById('restartCountdownModal');
        if (old) old.remove();

        var m = document.createElement('div');
        m.className = 'version-modal';
        m.id = 'restartCountdownModal';
        m.innerHTML =
            '<div class="version-modal-mask"></div>' +
            '<div class="version-modal-content" style="max-width:420px;text-align:center;">' +
                '<div class="version-modal-header">' +
                    '<h3 id="restartModalTitle">正在应用更新</h3>' +
                '</div>' +
                '<div style="padding:8px 0 6px;">' +
                    '<div class="countdown-ring-wrap" style="position:relative;width:140px;height:140px;margin:8px auto 4px;display:inline-block;">' +
                        '<svg class="countdown-ring" width="140" height="140" viewBox="0 0 140 140" style="transform:rotate(-90deg);">' +
                            '<circle class="countdown-ring-bg" cx="70" cy="70" r="58" fill="none" stroke="#e5e7eb" stroke-width="10" />' +
                            '<circle id="restartCountdownRing" class="countdown-ring-fg" cx="70" cy="70" r="58" fill="none" stroke="#10b981" stroke-width="10" stroke-linecap="round" ' +
                                'stroke-dasharray="364.42" stroke-dashoffset="0" ' +
                                'style="transition: stroke-dashoffset 0.25s linear;" />' +
                        '</svg>' +
                        '<div class="countdown-ring-text" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;">' +
                            '<div id="restartCountdown" style="font-size:26px;font-weight:700;color:#111827;line-height:1;">--</div>' +
                            '<div style="font-size:12px;color:#6b7280;margin-top:2px;">秒后自动刷新</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div id="restartMsg" style="line-height:1.7;font-size:14px;color:#334155;margin:6px 0 8px;">' +
                    esc(opts.prepareMsg || '正在重启服务并应用更新...') +
                '</div>' +
                '<div style="display:flex;gap:10px;justify-content:center;">' +
                    '<button id="restartRefreshBtn" style="display:none;padding:8px 18px;border:0;border-radius:6px;background:#10b981;color:#fff;cursor:pointer;font-size:14px;">立即刷新</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(m);

        var ring = document.getElementById('restartCountdownRing');
        var countdownEl = document.getElementById('restartCountdown');
        var msgEl = document.getElementById('restartMsg');
        var titleEl = document.getElementById('restartModalTitle');
        var refreshBtn = document.getElementById('restartRefreshBtn');
        var CIRC = 364.42;
        function close() { try { m.remove(); } catch (_) {} }

        if (refreshBtn) refreshBtn.onclick = function () { location.reload(true); };
        m.querySelector('.version-modal-mask').onclick = function () { /* 不允许点遮罩关闭 */ };

        var startTime = Date.now();
        var stopped = false;
        var timers = [];

        function setRing(pct) {
            var offset = Math.max(0, Math.min(1, pct)) * CIRC;
            if (ring) ring.setAttribute('stroke-dashoffset', offset.toFixed(2));
            var remainSec = Math.max(0, Math.ceil((1 - Math.max(0, Math.min(1, pct))) * (estimatedMs / 1000)));
            if (countdownEl) countdownEl.textContent = String(remainSec);
        }

        function pollOnce() {
            if (stopped) return;
            var url = (_deps.API_SUMMARY || '/api/summary') + '?_=' + Date.now();
            fetch(url, { cache: 'no-store', credentials: 'same-origin' })
                .then(function (r) {
                    if (!r.ok) throw new Error('not ok');
                    return r.text();
                })
                .then(function (txt) {
                    if (stopped) return;
                    if (txt && txt.length > 0) {
                        stopped = true;
                        try {
                            if (titleEl) titleEl.textContent = '更新完成';
                            if (msgEl) msgEl.textContent = '服务已恢复，即将自动刷新页面...';
                        } catch (_) {}
                        timers.forEach(function (t) { try { clearInterval(t); clearTimeout(t); } catch (_) {} });
                        timers = [];
                        safeReload(0, close, msgEl, refreshBtn);
                    }
                })
                .catch(function () { /* 未恢复，下一轮 */ });
        }

        setRing(0);
        timers.push(setInterval(function () {
            if (stopped) return;
            var elapsed = Date.now() - startTime;
            var pct = Math.max(0, Math.min(1, elapsed / estimatedMs));
            setRing(pct);
            if (pct >= 1) {
                try {
                    if (titleEl) titleEl.textContent = '等待服务恢复';
                    if (msgEl) msgEl.textContent = '服务重启时间较长，正在持续检测恢复，或点击"立即刷新"手动刷新页面';
                } catch (_) {}
            }
        }, 250));

        timers.push(setTimeout(function () {
            pollOnce();
            var maxPollUntil = Date.now() + 90000;
            var pollInterval = setInterval(function () {
                if (stopped) {
                    try { clearInterval(pollInterval); } catch (_) {}
                    return;
                }
                if (Date.now() > maxPollUntil) {
                    try { clearInterval(pollInterval); } catch (_) {}
                    if (!stopped && msgEl) {
                        msgEl.textContent = '检测超时，请点击"立即刷新"查看页面，若无法打开请手动重启启动脚本';
                    }
                    return;
                }
                pollOnce();
            }, 800);
            timers.push(pollInterval);
        }, 1200));
    }

    /**
     * safeReload —— 服务端端口重新 bind 后再 reload，避免 Chrome 错误页
     */
    function safeReload(attempt, close, msgEl, refreshBtn) {
        attempt = attempt || 0;
        if (attempt > 10) {
            try {
                if (msgEl) msgEl.innerHTML = '服务已恢复，请<a href="' + location.pathname + '" style="color:#10b981;text-decoration:underline;">点此手动刷新页面</a>';
                if (refreshBtn) refreshBtn.style.display = '';
            } catch (_) {}
            return;
        }
        var probeUrl = (_deps.API_SUMMARY || '/api/summary') + '?_=' + Date.now() + '&_retry=' + attempt;
        fetch(probeUrl, { cache: 'no-store', credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('not ok');
                return r.text();
            })
            .then(function (t) {
                if (!t || t.length === 0) throw new Error('empty');
                setTimeout(function () {
                    try { close && close(); } catch (_) {}
                    try { location.replace(location.pathname + location.search + location.hash); }
                    catch (_) { try { location.reload(true); } catch (_2) {} }
                }, 400);
            })
            .catch(function () { setTimeout(function () { safeReload(attempt + 1, close, msgEl, refreshBtn); }, 600); });
    }

    // —— 对外公开接口 ——
    function bindButtons(root) {
        var btn = (root || document).getElementById('checkUpdateBtn');
        if (btn) {
            btn.addEventListener('click', forceCheckUpdate);
        }
    }

    function initAutoCheck() {
        // 静默检查：如果有更新，在按钮上加个红点
        // 需求1：红点判断以「稳定通道最新版本」为依据
        try {
            fetch('/api/version/list', { cache: 'no-store' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data || data.error) return;
                    var local = data.local_version || '';
                    var latestStable = data.latest_stable_version || data.latest_version || '';
                    if (latestStable && local && latestStable !== local) {
                        _setUpdateDot(true);
                    }
                })
                .catch(function () { /* 静默忽略 */ });
        } catch (_) {}
    }

    function forceCheckUpdate() {
        return checkUpdate();
    }

    // —— 初始化入口：接收外部依赖注入 ——
    function useUpdate(deps) {
        if (deps) {
            if (typeof deps.showToast === 'function') _deps.showToast = deps.showToast;
            if (typeof deps.getPassword === 'function') _deps.getPassword = deps.getPassword;
            if (typeof deps.clearPassword === 'function') _deps.clearPassword = deps.clearPassword;
            if (typeof deps.escapeHtml === 'function') _deps.escapeHtml = deps.escapeHtml;
            if (typeof deps.API_SUMMARY === 'string' && deps.API_SUMMARY) _deps.API_SUMMARY = deps.API_SUMMARY;
        }
        return {
            bindButtons: bindButtons,
            initAutoCheck: initAutoCheck,
            forceCheckUpdate: forceCheckUpdate,
            _debug: {
                checkUpdate: checkUpdate,
                doDownloadUpdate: doDownloadUpdate,
                showRestartCountdownModal: showRestartCountdownModal,
            },
        };
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = useUpdate;
    else global.useUpdate = useUpdate;
})(typeof window !== 'undefined' ? window : this);
