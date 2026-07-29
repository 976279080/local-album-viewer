/**
 * 上传页面主逻辑
 * 依赖：config.js, constants.js, utils.js, exifr.js, media-processor.js, upload.css
 */
(function () {
    'use strict';

    const C = window.AppConstants;
    const U = window.AppUtils;

    const { getPassword, clearPassword, hasPassword } = usePassword();

    const DEFAULT_ALBUM_COLOR = (window.APP_CONFIG || {}).ui?.defaultAlbumColor ?? '#667eea';
    const ALBUM_NAME_MAX_LEN = (window.APP_CONFIG || {}).ui?.albumNameMaxLength ?? 50;
    const RENAME_ALBUM_MAX_LEN = (window.APP_CONFIG || {}).ui?.renameAlbumMaxLength ?? 15;
    const UPLOAD_BATCH_SIZE = (window.APP_CONFIG || {}).upload?.batchSize ?? 2;
    const UPLOAD_TIMEOUT_MS = (window.APP_CONFIG || {}).upload?.timeoutMs ?? 120000;
    const API_SUMMARY = (window.APP_CONFIG || {}).api?.summary ?? '/api/summary';
    const API_RENAME_ALBUM = (window.APP_CONFIG || {}).api?.renameAlbum ?? '/api/rename-album';
    const API_UPLOAD = (window.APP_CONFIG || {}).api?.upload ?? '/api/upload';

    let selectedFiles = [];
    let processedFiles = [];
    let selectedAlbumName = '';
    let selectedAlbumId = '';
    let albumDropdownTimeout = null;
    let cachedAlbums = null;
    let isUploading = false;
    let abortController = null;
    let licenseStatus = null;

    let albumInput, dropZone, fileInput, fileList, fileCount, submitBtn;
    let progressContainer, progressFill, progressPercent, progressStage, progressDetail;
    let progressFile, progressFileFill;
    let albumDropdown, albumChipBadges;

    function init() {
        albumInput = document.getElementById('albumInput');
        dropZone = document.getElementById('dropZone');
        fileInput = document.getElementById('fileInput');
        fileList = document.getElementById('fileList');
        fileCount = document.getElementById('fileCount');
        submitBtn = document.getElementById('submitBtn');
        progressContainer = document.getElementById('progressContainer');
        progressFill = document.getElementById('progressFill');
        progressPercent = document.getElementById('progressPercent');
        progressStage = document.getElementById('progressStage');
        progressDetail = document.getElementById('progressDetail');
        progressFile = document.getElementById('progressFile');
        progressFileFill = document.getElementById('progressFileFill');
        albumDropdown = document.getElementById('albumDropdown');
        albumChipBadges = document.getElementById('albumChipBadges');

        albumInput.maxLength = ALBUM_NAME_MAX_LEN;

        bindEvents();
        loadAlbums();
        updateUI();

        // 版本检查
        document.getElementById('checkUpdateBtn').addEventListener('click', checkUpdate);

        // 授权状态
        document.getElementById('licenseActionBtn').addEventListener('click', handleLicenseAction);
        loadLicenseStatus();
    }

    /**
     * 使用 XMLHttpRequest 上传文件，支持真实上传进度回调
     */
    function uploadFileWithProgress(url, formData, opts) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', url);
            xhr.setRequestHeader('X-Auth', opts.password);
            xhr.timeout = opts.timeoutMs;

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable && opts.onProgress) {
                    opts.onProgress(e.loaded, e.total);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 401) {
                    reject(new Error('密码错误'));
                } else if (xhr.status >= 400) {
                    let errorMsg = '上传失败';
                    try {
                        const err = JSON.parse(xhr.responseText);
                        errorMsg = err.error || '上传失败';
                        if (errorMsg.includes('特殊字符')) {
                            errorMsg = '相册名称不能包含特殊字符';
                        }
                    } catch (e) {}
                    reject(new Error(errorMsg));
                } else {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch (e) { resolve({}); }
                }
            };

            xhr.onerror = () => reject(new Error('网络错误'));
            xhr.ontimeout = () => reject(new Error('上传超时'));
            xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'));

            const signal = opts.abortSignal;
            if (signal) {
                if (signal.aborted) { xhr.abort(); return; }
                signal.addEventListener('abort', () => xhr.abort(), { once: true });
            }

            xhr.send(formData);
        });
    }

    function bindEvents() {
        albumInput.onfocus = () => showAlbumDropdown();
        albumInput.oninput = () => showAlbumDropdown();
        albumInput.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = albumInput.value.trim();
                if (val) {
                    selectAlbum('', val, DEFAULT_ALBUM_COLOR);
                }
            }
        };

        dropZone.onclick = () => {
            if (!isUploading) fileInput.click();
        };
        dropZone.ondragover = (e) => {
            e.preventDefault();
            if (!isUploading) dropZone.classList.add('dragover');
        };
        dropZone.ondragleave = () => dropZone.classList.remove('dragover');
        dropZone.ondrop = (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (!isUploading) addFiles(e.dataTransfer.files);
        };

        fileInput.onchange = () => {
            addFiles(fileInput.files);
            fileInput.value = '';
        };

        document.getElementById('uploadForm').onsubmit = handleSubmit;

        document.addEventListener('click', (e) => {
            const createAlbumOption = e.target.closest('.create-album-option');
            if (createAlbumOption) {
                const name = albumInput.value.trim();
                if (name) {
                    selectAlbum('', name, DEFAULT_ALBUM_COLOR);
                }
                return;
            }
            if (!e.target.closest('.tag-input-inline')) {
                albumDropdown.classList.remove('show');
            }
        });
    }

    async function loadAlbums() {
        try {
            const res = await fetch(API_SUMMARY);
            const data = await res.json();
            cachedAlbums = data;
        } catch (e) {
            console.error('加载相册失败', e);
        }
    }

    function renderAlbumChip() {
        if (selectedAlbumName) {
            const color = cachedAlbums?.members?.[selectedAlbumId]?.color || DEFAULT_ALBUM_COLOR;
            albumChipBadges.innerHTML = `<span class="tag-badge" style="background:${color}">${selectedAlbumName} <span class="remove" onclick="window.UploadApp.clearAlbumSelection()">×</span>${selectedAlbumId ? `<span class="rename" onclick="window.UploadApp.showRenameAlbum()" style="margin-left:4px;cursor:pointer;opacity:0.7;font-size:10px;" title="重命名相册">✎</span>` : ''}</span>`;
        } else {
            albumChipBadges.innerHTML = '';
        }
    }

    function showRenameAlbum() {
        if (!selectedAlbumId || !selectedAlbumName) return;

        const modal = document.createElement('div');
        modal.className = 'password-modal';
        modal.id = 'renameModal';
        modal.innerHTML = `
            <div class="password-modal-content">
                <h3>重命名相册</h3>
                <input type="text" id="renameInput" value="${escapeHtml(selectedAlbumName)}" placeholder="新相册名称（最多${RENAME_ALBUM_MAX_LEN}字）" autofocus>
                <button id="renameSubmitBtn" style="background:#667eea;margin-bottom:8px;">确认重命名</button>
                <button onclick="window.UploadApp.closeRenameModal()" style="background:#f5f5f5;color:#333;">取消</button>
            </div>
        `;
        document.body.appendChild(modal);

        const input = document.getElementById('renameInput');
        const submitBtnEl = document.getElementById('renameSubmitBtn');

        input.focus();
        input.select();
        input.maxLength = RENAME_ALBUM_MAX_LEN;

        let isRenaming = false;
        submitBtnEl.onclick = async () => {
            if (isRenaming) return;
            const newName = input.value.trim();
            if (!newName) {
                showToast('请输入新名称', 'warning');
                return;
            }
            if (newName.length > RENAME_ALBUM_MAX_LEN) {
                showToast(`名称最多${RENAME_ALBUM_MAX_LEN}字`, 'warning');
                return;
            }
            if (U.hasIllegalChars(newName)) {
                showToast(`相册名称不能包含特殊字符：${C.ILLEGAL_CHARS_STR}`, 'error');
                return;
            }

            const { getPassword, clearPassword } = usePassword();
            const password = await getPassword();
            if (!password) return;

            isRenaming = true;
            submitBtnEl.disabled = true;
            submitBtnEl.textContent = '重命名中...';
            try {
                const res = await fetch(API_RENAME_ALBUM, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Auth': password },
                    body: JSON.stringify({ album_id: selectedAlbumId, name: newName })
                });

                if (res.status === 401) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return;
                }

                const result = await res.json();
                if (result.status === 'ok') {
                    selectedAlbumName = newName;
                    if (result.album_id) {
                        selectedAlbumId = result.album_id;
                    }
                    renderAlbumChip();
                    closeRenameModal();
                    showToast(result.message || '相册已重命名', 'success');
                    if (cachedAlbums && cachedAlbums.members) {
                        if (cachedAlbums.members[selectedAlbumId]) {
                            cachedAlbums.members[selectedAlbumId].name = newName;
                        }
                    }
                } else {
                    showToast(result.error || '重命名失败', 'error');
                }
            } catch (e) {
                showToast('重命名失败', 'error');
            } finally {
                isRenaming = false;
                submitBtnEl.disabled = false;
                submitBtnEl.textContent = '确认重命名';
            }
        };

        input.onkeydown = (e) => {
            if (e.key === 'Enter') submitBtnEl.click();
            if (e.key === 'Escape') closeRenameModal();
        };

        modal.onclick = (e) => {
            if (e.target === modal) closeRenameModal();
        };
    }

    function closeRenameModal() {
        const modal = document.getElementById('renameModal');
        if (modal) modal.remove();
    }

    function showAlbumDropdown() {
        if (!cachedAlbums) return;

        const filter = albumInput.value.trim().toLowerCase();
        const members = cachedAlbums.members || {};

        const options = Object.entries(members)
            .filter(([id, info]) => !filter || info.name.toLowerCase().includes(filter))
            .filter(([id]) => id !== selectedAlbumId);

        if (options.length === 0 && !filter) {
            albumDropdown.classList.remove('show');
            return;
        }

        albumDropdown.innerHTML = options.map(([id, info]) => `
            <div class="tag-option" onclick="window.UploadApp.selectAlbum('${id}', '${info.name}', '${info.color}')">
                <span class="tag-color" style="background:${info.color}"></span>
                ${info.name}
            </div>
        `).join('');

        if (filter) {
            const exists = Object.values(members).some(info => info.name.toLowerCase() === filter.toLowerCase());
            if (!exists) {
                const escapedFilter = escapeHtml(filter);
                albumDropdown.innerHTML += `
                    <div class="tag-option create-album-option" style="color:#667eea;">
                        + 创建相册 "${escapedFilter}"
                    </div>
                `;
            }
        }

        albumDropdown.classList.add('show');
    }

    function selectAlbum(id, name, color) {
        if (!id && U.hasIllegalChars(name)) {
            showToast(`相册名称不能包含特殊字符：${C.ILLEGAL_CHARS_STR}`, 'error');
            return;
        }
        selectedAlbumId = id;
        selectedAlbumName = name;
        renderAlbumChip();
        albumInput.value = '';
        albumDropdown.classList.remove('show');
        updateUI();
    }

    function clearAlbumSelection() {
        selectedAlbumId = '';
        selectedAlbumName = '';
        renderAlbumChip();
        albumInput.value = '';
        albumInput.focus();
        updateUI();
    }

    function addFiles(files) {
        let added = 0;
        for (const f of files) {
            if (!selectedFiles.find(sf => sf.name === f.name && sf.size === f.size)) {
                selectedFiles.push(f);
                added++;
            }
        }
        if (added > 0) {
            showToast(`已添加 ${added} 个文件`, 'info');
        }
        updateUI();
    }

    function removeFile(index) {
        if (isUploading) return;
        selectedFiles.splice(index, 1);
        processedFiles.splice(index, 1);
        updateUI();
    }

    function updateUI() {
        const totalSize = selectedFiles.reduce((sum, f) => sum + f.size, 0);
        fileCount.textContent = selectedFiles.length > 0
            ? `(${selectedFiles.length} 个文件，约 ${U.formatFileSize(totalSize)})`
            : '';

        renderFileList();

        const album = selectedAlbumName || albumInput.value.trim();
        submitBtn.disabled = selectedFiles.length === 0 || !album || isUploading;
        submitBtn.textContent = isUploading ? '上传中...' : '开始上传';

        if (isUploading) {
            dropZone.classList.add('disabled');
        } else {
            dropZone.classList.remove('disabled');
        }

        if (!isUploading) {
            progressContainer.classList.remove('show');
        }
    }

    function renderFileList() {
        fileList.innerHTML = selectedFiles.map((f, i) => {
            let statusClass = '';
            let statusText = U.formatFileSize(f.size);

            if (processedFiles[i]) {
                if (processedFiles[i].error) {
                    statusClass = 'error';
                    statusText = '处理失败';
                } else if (processedFiles[i].thumbnail) {
                    statusClass = 'success';
                    statusText = '已处理';
                } else if (isUploading) {
                    statusClass = 'processing';
                    statusText = '处理中...';
                }
            }

            return `
                <div class="file-item ${statusClass}">
                    <span class="file-item-name">${escapeHtml(f.name)}</span>
                    <span class="file-item-status">${statusText}</span>
                    <span class="file-item-remove" onclick="window.UploadApp.removeFile(${i})">×</span>
                </div>
            `;
        }).join('');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    async function handleSubmit(e) {
        e.preventDefault();

        if (isUploading) {
            if (abortController) {
                abortController.abort();
            }
            isUploading = false;
            updateUI();
            showToast('已取消上传', 'warning');
            return;
        }

        const album = selectedAlbumName || albumInput.value.trim();
        if (!album) {
            showToast('请输入相册名', 'warning');
            return;
        }

        if (U.hasIllegalChars(album)) {
            showToast(`相册名称不能包含特殊字符：${C.ILLEGAL_CHARS_STR}`, 'error');
            return;
        }

        if (selectedFiles.length === 0) {
            showToast('请选择要上传的文件', 'warning');
            return;
        }

        const password = await getPassword();
        if (!password) return;

        isUploading = true;
        abortController = new AbortController();
        updateUI();

        progressContainer.classList.add('show');
        progressFill.style.width = '0%';
        progressPercent.textContent = '0%';
        progressStage.textContent = '第 1 步：处理文件...';
        progressDetail.textContent = '正在读取文件信息、生成缩略图...';
        progressFile.style.display = 'none';
        progressFileFill.style.width = '0%';

        try {
            let successCount = 0;
            let failCount = 0;
            const failedFiles = [];

            const BATCH_SIZE = UPLOAD_BATCH_SIZE;
            const totalCount = selectedFiles.length;
            let completedCount = 0;
            const fileProgress = {};

            function updateUploadProgress() {
                const partialSum = Object.values(fileProgress).reduce((a, b) => a + b, 0);
                const overall = Math.min(((completedCount + partialSum) / totalCount) * 100, 100);
                progressFill.style.width = overall.toFixed(1) + '%';
                progressPercent.textContent = Math.round(overall) + '%';
            }

            for (let batchStart = 0; batchStart < selectedFiles.length; batchStart += BATCH_SIZE) {
                if (abortController && abortController.signal.aborted) {
                    break;
                }

                const batchEnd = Math.min(batchStart + BATCH_SIZE, selectedFiles.length);
                const batch = selectedFiles.slice(batchStart, batchEnd);

                const batchPromises = batch.map((file, idx) => {
                    const globalIdx = batchStart + idx;
                    return new Promise(async (resolve) => {
                        const progress = ((globalIdx + 1) / selectedFiles.length * 100).toFixed(0);

                        try {
                            progressStage.textContent = '处理文件...';
                            progressDetail.textContent = `处理中: ${file.name} (${globalIdx + 1}/${selectedFiles.length})`;
                            progressFill.style.width = progress + '%';
                            progressPercent.textContent = progress + '%';

                            const processed = await MediaProcessor.processFile(file);
                            processed.file = file;
                            processed.globalIdx = globalIdx;

                            resolve({ success: true, data: processed });
                        } catch (err) {
                            console.error(`处理失败: ${file.name}`, err);
                            resolve({ success: false, globalIdx, file, error: err.message });
                        }
                    });
                });

                const batchResults = await Promise.all(batchPromises);

                const uploadPromises = batchResults.filter(r => r.success).map(result => {
                    const processed = result.data;
                    return new Promise(async (resolve) => {
                        try {
                            progressStage.textContent = '第 2 步：上传文件...';
                            progressDetail.textContent = `上传中: ${processed.file.name}`;
                            progressFile.style.display = 'block';
                            progressFileFill.style.width = '0%';

                            const formData = new FormData();
                            formData.append('album', album);
                            formData.append('new_album', '');
                            formData.append('tags', JSON.stringify([]));
                            formData.append('width', processed.width || 0);
                            formData.append('height', processed.height || 0);
                            formData.append('create_time', processed.createTime || '');
                            // HEIC 已在前端转为 JPEG，上传转换后的文件
                            const uploadFile = processed.convertedFile || processed.file;
                            formData.append('size', uploadFile.size || 0);
                            formData.append('file', uploadFile);
                            if (processed.thumbnailBlob) {
                                formData.append('thumbnail', processed.thumbnailBlob, 'thumb.webp');
                            }

                            await uploadFileWithProgress(API_UPLOAD, formData, {
                                password,
                                timeoutMs: UPLOAD_TIMEOUT_MS,
                                abortSignal: abortController ? abortController.signal : null,
                                onProgress: (loaded, total) => {
                                    const ratio = total > 0 ? loaded / total : 0;
                                    fileProgress[processed.globalIdx] = ratio;
                                    updateUploadProgress();
                                    progressFileFill.style.width = (ratio * 100).toFixed(1) + '%';
                                    progressDetail.textContent = `上传中: ${processed.file.name} (${Math.round(ratio * 100)}%)`;
                                }
                            });

                            successCount++;
                            completedCount++;
                            delete fileProgress[processed.globalIdx];
                            updateUploadProgress();
                            processedFiles[processed.globalIdx] = { ...processed, status: 'uploaded' };
                            resolve({ success: true });
                        } catch (err) {
                            console.error(`上传失败: ${processed.file.name}`, err);
                            failCount++;
                            completedCount++;
                            delete fileProgress[processed.globalIdx];
                            updateUploadProgress();
                            failedFiles.push(processed.file);
                            processedFiles[processed.globalIdx] = {
                                originalName: processed.file.name,
                                size: processed.file.size,
                                error: err.message
                            };
                            resolve({ success: false });
                        } finally {
                            if (processed.thumbnailBlob) {
                                URL.revokeObjectURL(processed.thumbnailBlob);
                            }
                        }
                    });
                });

                await Promise.all(uploadPromises);

                batchResults.filter(r => !r.success).forEach(result => {
                    failCount++;
                    failedFiles.push(result.file);
                    processedFiles[result.globalIdx] = {
                        originalName: result.file.name,
                        size: result.file.size,
                        error: result.error
                    };
                });

                renderFileList();
                await new Promise(resolve => setTimeout(resolve, 0));
            }

            if (successCount > 0) {
                showToast(`成功上传 ${successCount} 个文件${failCount > 0 ? `，${failCount} 个失败` : ''}`,
                    failCount > 0 ? 'warning' : 'success');
                selectedFiles = failedFiles;
                processedFiles = [];
            } else {
                showToast('上传失败', 'error');
            }

        } catch (err) {
            if (err.name === 'AbortError') {
                showToast('已取消上传', 'warning');
            } else {
                console.error('上传错误:', err);
                showToast('上传失败: ' + err.message, 'error');
            }
        } finally {
            isUploading = false;
            abortController = null;
            progressFile.style.display = 'none';
            updateUI();
        }
    }

    function showToast(msg, type) {
        type = type || 'info';
        var container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        var icons = { success: '✓', error: '✕', warning: '!', info: 'i' };
        var toast = document.createElement('div');
        toast.className = 'toast-item toast-' + type;
        toast.innerHTML = '<span class="toast-icon">' + (icons[type] || 'i') + '</span><span style="flex:1;line-height:1.4;">' + msg + '</span>';
        container.appendChild(toast);
        setTimeout(function() { toast.remove(); }, C.NOTIFICATION_DURATION);
    }

    // 版本检查
    async function checkUpdate() {
        const btn = document.getElementById('checkUpdateBtn');
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9c2.5 0 4.8 1 6.5 2.6"/><polyline points="21 4 21 10 15 10"/></svg>加载中...';

        try {
            const res = await fetch('/api/version/list');
            const data = await res.json();

            if (data.error) {
                showToast('获取版本信息失败，请确认网络正常', 'error');
                return;
            }

            showVersionModal(data);
        } catch (e) {
            showToast('检查更新失败，请确认网络正常', 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    }

    function showVersionModal(data) {
        const existing = document.getElementById('versionModal');
        if (existing) existing.remove();

        const localVersion = data.local_version || '未知';
        const versions = data.versions || [];
        const latestVersion = data.latest_version || '';

        let versionsHtml = '';
        if (versions.length === 0) {
            versionsHtml = '<div class="version-empty">暂无版本信息</div>';
        } else {
            versionsHtml = versions.map(function(v) {
                var isCurrent = v.version === localVersion;
                var changelogHtml = (v.changelog || '暂无更新说明')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/### (.+)/g, '<strong>$1</strong>')
                    .replace(/^- (.+)$/gm, '<div class="changelog-item">• $1</div>');
                var actionHtml = '';
                if (isCurrent) {
                    actionHtml = '<span class="version-current-tag">当前版本</span>';
                } else if (v.download_url) {
                    actionHtml = '<button class="version-update-btn" data-url="' + v.download_url + '">更新到此版本</button>';
                } else {
                    actionHtml = '<span class="version-no-download">暂无下载地址</span>';
                }
                return '<div class="version-item' + (isCurrent ? ' current' : '') + '">' +
                    '<div class="version-item-header">' +
                        '<span class="version-number">v' + v.version + '</span>' +
                        '<span class="version-date">' + (v.date || '') + '</span>' +
                        actionHtml +
                    '</div>' +
                    '<div class="version-changelog">' + changelogHtml + '</div>' +
                '</div>';
            }).join('');
        }

        var hasUpdate = latestVersion && latestVersion !== localVersion;

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
                    '当前版本：<span class="version-current-badge">v' + localVersion + '</span>' +
                    (hasUpdate ? '<span class="version-new-badge">有新版本 v' + latestVersion + '</span>' : '<span class="version-latest-badge">已是最新</span>') +
                '</div>' +
                '<div class="version-modal-tip">下载新版本后，点击入口文件重启即可完成更新</div>' +
                '<div class="version-modal-list">' + versionsHtml + '</div>' +
            '</div>';

        document.body.appendChild(modal);

        modal.querySelector('.version-modal-mask').onclick = function() { modal.remove(); };
        modal.querySelector('.version-modal-close').onclick = function() { modal.remove(); };

        var updateBtns = modal.querySelectorAll('.version-update-btn');
        for (var i = 0; i < updateBtns.length; i++) {
            updateBtns[i].onclick = function() {
                window.open(this.getAttribute('data-url'), '_blank');
            };
        }
    }

    // ============ 授权状态管理 ============
    async function loadLicenseStatus() {
        try {
            const res = await fetch('/api/license/status');
            const data = await res.json();
            licenseStatus = data;
            renderLicenseStatus(data);
        } catch (e) {
            console.error('加载授权状态失败:', e);
            document.getElementById('licenseValue').textContent = '获取失败';
        }
    }

    function renderLicenseStatus(data) {
        const areaEl = document.getElementById('licenseStatusArea');
        const valueEl = document.getElementById('licenseValue');
        const btnEl = document.getElementById('licenseActionBtn');

        valueEl.className = 'license-value';

        let shouldShow = false;

        if (data.has_license) {
            shouldShow = true;
            if (data.license_type === 'permanent') {
                valueEl.textContent = '永久授权';
                valueEl.classList.add('active');
                // 永久码：隐藏按钮
                btnEl.style.display = 'none';
            } else {
                const typeName = data.license_type === 'monthly' ? '月卡' : '年卡';
                if (data.remaining_days <= 10) {
                    valueEl.textContent = `${typeName}剩余 ${data.remaining_days} 天`;
                    valueEl.classList.add('expiring');
                } else {
                    valueEl.textContent = `${typeName}剩余 ${data.remaining_days} 天`;
                    valueEl.classList.add('active');
                }
                btnEl.style.display = '';
                btnEl.textContent = '续费叠加';
            }
        } else if (data.first_upload_time === null) {
            shouldShow = false;
        } else if (data.in_free_trial) {
            if (data.free_trial_remaining_days <= 30) {
                shouldShow = true;
                valueEl.textContent = `免费期剩余 ${data.free_trial_remaining_days} 天`;
                valueEl.classList.add('inactive');
            } else {
                shouldShow = false;
            }
            btnEl.style.display = shouldShow ? '' : 'none';
            btnEl.textContent = '激活授权码';
        } else {
            shouldShow = true;
            valueEl.textContent = '已过期，需激活授权码';
            valueEl.classList.add('inactive');
            btnEl.style.display = '';
            btnEl.textContent = '激活授权码';
        }

        areaEl.style.display = shouldShow ? 'flex' : 'none';
    }

    async function handleLicenseAction() {
        const code = await showLicenseCodeModal();
        if (!code) return;

        try {
            const res = await fetch('/api/license/activate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.success) {
                showToast(data.message || '授权成功', 'success');
                await loadLicenseStatus();
            } else {
                showToast(data.message || data.error || '授权失败，请检查授权码后重试', 'error');
            }
        } catch (e) {
            showToast('网络异常，请稍后重试', 'error');
        }
    }

    async function showLicenseCodeModal() {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'license-modal';
            modal.innerHTML = `
                <div class="license-modal-mask"></div>
                <div class="license-modal-content">
                    <h3 class="license-modal-title">输入授权码</h3>
                    <p class="license-modal-hint">请输入您购买的授权码</p>
                    <input type="text" id="license-code-input" class="license-code-input" placeholder="粘贴或输入授权码" autocomplete="off">
                    <div class="license-modal-subscribe">
                        <a href="/subscribe.html" target="_blank">没有授权码？去订阅</a>
                    </div>
                    <div class="license-modal-actions">
                        <button class="license-modal-btn license-modal-btn-cancel" id="license-cancel">取消</button>
                        <button class="license-modal-btn license-modal-btn-confirm" id="license-confirm">确定</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            const input = modal.querySelector('#license-code-input');
            const confirmBtn = modal.querySelector('#license-confirm');
            const cancelBtn = modal.querySelector('#license-cancel');
            const mask = modal.querySelector('.license-modal-mask');

            const close = () => modal.remove();

            const doSubmit = () => {
                const val = input.value.trim();
                close();
                resolve(val);
            };

            confirmBtn.onclick = doSubmit;
            cancelBtn.onclick = () => { close(); resolve(''); };
            mask.onclick = () => { close(); resolve(''); };
            input.onkeydown = (e) => {
                if (e.key === 'Enter') doSubmit();
                if (e.key === 'Escape') { close(); resolve(''); }
            };

            setTimeout(() => input.focus(), 50);
        });
    }

    window.UploadApp = {
        init,
        selectAlbum,
        clearAlbumSelection,
        showRenameAlbum,
        closeRenameModal,
        removeFile
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
