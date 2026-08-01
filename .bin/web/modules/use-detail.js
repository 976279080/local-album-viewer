/**
 * 详情页 composable - 详情页打开/关闭、导航、保存、删除、评论、时间编辑
 * 遵循单一职责原则：仅负责详情页相关逻辑
 * 依赖：外部传入的 ui/basePhotos/albumPhotos 等对象、Api、showToast 等
 */
(function () {
    'use strict';

    function useDetail(
        ui, detailState, basePhotos, albumPhotos, visiblePhotos, editCreateTime, tagInputValue, summary,
        refreshComputedCallback, loadSummaryCallback, loadPhotosCallback,
        showToast, getPassword, clearPassword, showConfirm,
        validateText, validateComment, toggleBatchModeCallback, albumYearList,
        openDropdown,
        updatePhotoInListsFn, removePhotoFromListsFn, removePhotosFromListsFn
    ) {
        const C = window.AppConstants;
        const U = window.AppUtils;
        const Api = window.AppApi;
        const VIDEO_PROGRESS_KEY = 'qorder_video_progress';
        let videoPlaybackRate = 1.0;
        let isVideoNavigation = false;
        let openDetailToken = 0;  // openDetail 并发令牌：过期请求的 await 结果不更新 UI

        function getVideoProgressMap() {
            try {
                return JSON.parse(localStorage.getItem(VIDEO_PROGRESS_KEY) || '{}');
            } catch (e) {
                return {};
            }
        }

        function saveVideoProgress(photoId, currentTime) {
            if (!photoId || !currentTime || currentTime < 1) return;
            try {
                const map = getVideoProgressMap();
                map[photoId] = Math.floor(currentTime);
                localStorage.setItem(VIDEO_PROGRESS_KEY, JSON.stringify(map));
            } catch (e) {}
        }

        function getVideoProgress(photoId) {
            if (!photoId) return 0;
            try {
                const map = getVideoProgressMap();
                return map[photoId] || 0;
            } catch (e) {
                return 0;
            }
        }

        function clearVideoProgress(photoId) {
            if (!photoId) return;
            try {
                const map = getVideoProgressMap();
                delete map[photoId];
                localStorage.setItem(VIDEO_PROGRESS_KEY, JSON.stringify(map));
            } catch (e) {}
        }

        function saveCurrentVideoProgress() {
            const video = document.querySelector('.detail-left video');
            if (video && detailState.detailPhoto && detailState.detailPhoto.file_type === 'video') {
                saveVideoProgress(detailState.detailPhoto.id, video.currentTime);
            }
        }

        function restoreVideoProgress() {
            const video = document.querySelector('.detail-left video');
            if (video && detailState.detailPhoto && detailState.detailPhoto.file_type === 'video') {
                if (videoPlaybackRate !== 1.0) {
                    video.playbackRate = videoPlaybackRate;
                }
                const savedTime = getVideoProgress(detailState.detailPhoto.id);
                if (savedTime > 0 && isFinite(video.duration) && savedTime < (video.duration - 1)) {
                    try {
                        video.currentTime = savedTime;
                    } catch (e) {}
                }
            }
        }

        // ============ 详情面板 ============
        async function openDetail(photo) {
            const token = ++openDetailToken;
            detailState.showDetail = true;
            detailState.fileExists = true;
            ui.commentInput = '';
            ui.showCommentInput = false;
            tagInputValue.value = '';
            ui.showTagDropdown = false;
            editCreateTime.value = '';
            detailState.originalDetailPhoto = null;
            openDropdown.value = null;

            document.body.classList.add('detail-open');

            document.addEventListener('keydown', handleDetailKeydown, true);
            document.addEventListener('fullscreenchange', handleFullscreenChange);

            detailState.detailPhoto = JSON.parse(JSON.stringify(photo));
            // compact 数据不含详情字段，设默认空字符串避免首次渲染显示"-"
            if (!detailState.detailPhoto.absolute_path) detailState.detailPhoto.absolute_path = '';
            if (!detailState.detailPhoto.size) detailState.detailPhoto.size = 0;
            if (!detailState.detailPhoto.width) detailState.detailPhoto.width = 0;
            if (!detailState.detailPhoto.height) detailState.detailPhoto.height = 0;
            if (!detailState.detailPhoto.filename) detailState.detailPhoto.filename = '';
            if (!detailState.detailPhoto.album_name) detailState.detailPhoto.album_name = '';
            if (!detailState.detailPhoto.upload_time) detailState.detailPhoto.upload_time = '';
            if (!detailState.detailPhoto.edit_count) detailState.detailPhoto.edit_count = 0;
            detailState.detailPhoto.comments = [];
            initEditCreateTime();

            preloadNextPhoto();

            if (photo.file_type === 'video') {
                setTimeout(() => {
                    const video = document.querySelector('.detail-left video');
                    if (video) {
                        if (isVideoNavigation) {
                            video.load();
                            isVideoNavigation = false;
                        }
                        video.focus();
                    }
                }, 50);
            }

            setTimeout(() => {
                detailState.currentPhotoIndex = visiblePhotos.value.findIndex(p => p.path_key === photo.path_key);
            }, 0);

            try {
                const data = await Api.fetchPhotoDetail(photo.id);
                if (token !== openDetailToken) return;
                if (data.status === 'ok') {
                    detailState.detailPhoto = data.photo;
                    initEditCreateTime();
                    detailState.originalDetailPhoto = snapshotDetailPhoto(detailState.detailPhoto);
                } else {
                    detailState.originalDetailPhoto = snapshotDetailPhoto(detailState.detailPhoto);
                }
            } catch (e) {
                if (token !== openDetailToken) return;
                console.error('Failed to load photo detail:', e);
                detailState.originalDetailPhoto = snapshotDetailPhoto(detailState.detailPhoto);
            }
        }

        function snapshotDetailPhoto(photo) {
            return {
                title: photo.title || '',
                rating: photo.rating || 0,
                tags: Array.isArray(photo.tags) ? [...photo.tags] : []
            };
        }

        function preloadNextPhoto() {
            const ni = detailState.currentPhotoIndex + 1;
            if (ni >= 0 && ni < visiblePhotos.value.length) {
                const next = visiblePhotos.value[ni];
                if (next.file_type !== 'video') {
                    const img = new Image();
                    img.src = next.original_url;
                }
            }
        }

        function handleFullscreenChange() {
            const video = document.querySelector('.detail-left video');
            if (video && document.fullscreenElement) {
                video.focus();
            }
        }

        function closeDetail() {
            saveCurrentVideoProgress();
            openDetailToken++;  // 使正在进行的 openDetail 请求过期，不再更新 UI
            detailState.showDetail = false;
            detailState.detailPhoto = null;
            ui.showLargeViewer = false;
            ui.commentInput = '';
            ui.showCommentInput = false;
            videoPlaybackRate = 1.0;
            isVideoNavigation = false;

            document.body.classList.remove('detail-open');

            document.removeEventListener('keydown', handleDetailKeydown, true);
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
        }

        function handleDetailLeftClick(e) {
            if (e.target === e.currentTarget) {
                closeDetail();
            } else if (e.target.tagName === 'IMG') {
                closeDetail();
            }
        }

        function toggleVideoPlay(e) {
            const video = e ? e.currentTarget : document.querySelector('.detail-left video');
            if (!video || video.tagName !== 'VIDEO') return;
            if (e) {
                const rect = video.getBoundingClientRect();
                const controlHeight = 60;
                if (e.clientY - rect.top > rect.height - controlHeight) {
                    return;
                }
                e.preventDefault();
            }
            if (video.paused) {
                video.play();
            } else {
                video.pause();
            }
        }

        function onVideoEnded() {
            if (detailState.detailPhoto) {
                clearVideoProgress(detailState.detailPhoto.id);
            }
        }

        function onVideoKeydown(e) {
            const video = e.target;
            if (e.code === 'Space' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                if (video.paused) {
                    video.play();
                } else {
                    video.pause();
                }
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                e.stopPropagation();
                if (isFinite(video.duration)) {
                    video.currentTime = Math.min(video.currentTime + 5, video.duration);
                }
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                e.stopPropagation();
                video.currentTime = Math.max(video.currentTime - 5, 0);
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                e.stopPropagation();
                navPhoto(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                e.stopPropagation();
                navPhoto(-1);
            }
        }

        function handleDetailKeydown(e) {
            if (!detailState.showDetail) return;
            const video = document.querySelector('.detail-left video');
            const isVideoTarget = video && (e.target === video || video.contains(e.target));
            if (e.key === 'ArrowDown') {
                if (isVideoTarget) return;
                e.preventDefault();
                navPhoto(1);
            } else if (e.key === 'ArrowUp') {
                if (isVideoTarget) return;
                e.preventDefault();
                navPhoto(-1);
            } else if (video && e.key === 'ArrowRight') {
                if (isVideoTarget) return;
                e.preventDefault();
                e.stopPropagation();
                if (isFinite(video.duration)) {
                    video.currentTime = Math.min(video.currentTime + 5, video.duration);
                }
            } else if (video && e.key === 'ArrowLeft') {
                if (isVideoTarget) return;
                e.preventDefault();
                e.stopPropagation();
                video.currentTime = Math.max(video.currentTime - 5, 0);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closeDetail();
            } else if (e.code === 'Space' || e.key === ' ') {
                if (video) {
                    if (isVideoTarget) return;
                    e.preventDefault();
                    e.stopPropagation();
                    if (video.paused) {
                        video.play();
                    } else {
                        video.pause();
                    }
                }
            }
        }

        function navPhoto(dir) {
            saveCurrentVideoProgress();
            const ni = detailState.currentPhotoIndex + dir;
            if (ni < 0) {
                showToast('已经是第一张了', 'warning');
                return;
            }
            if (ni >= visiblePhotos.value.length) {
                showToast('已经是最后一张了', 'warning');
                return;
            }
            const currentVideo = document.querySelector('.detail-left video');
            const nextPhoto = visiblePhotos.value[ni];
            const nextIsVideo = nextPhoto.file_type === 'video';
            if (currentVideo && nextIsVideo) {
                videoPlaybackRate = currentVideo.playbackRate || 1.0;
                isVideoNavigation = true;
            } else {
                videoPlaybackRate = 1.0;
                isVideoNavigation = false;
            }
            openDetail(nextPhoto);
        }

        // ============ 保存照片 ============
        async function savePhoto() {
            if (!detailState.detailPhoto) return false;
            try {
                if (!validateText(detailState.detailPhoto.title, '标题')) return false;

                for (const tag of (detailState.detailPhoto.tags || [])) {
                    if (!validateText(tag, '标签')) return false;
                }

                let commentAdded = false;
                if (ui.commentInput.trim()) {
                    if (!validateComment(ui.commentInput.trim(), '评论')) return false;

                    const commentText = ui.commentInput.trim();
                    ui.commentInput = '';
                    ui.showCommentInput = false;

                    const cr = await Api.authFetch(C.API.commentAdd, {
                        method: 'POST',
                        body: JSON.stringify({
                            photo_id: detailState.detailPhoto.id,
                            text: commentText
                        })
                    });
                    const cdata = await cr.json();
                    if (cdata.status === 'ok') {
                        const newComment = {
                            id: cdata.comment_id,
                            text: commentText,
                            created_at: new Date().toISOString()
                        };
                        const nowTs = Math.floor(Date.now() / 1000);
                        detailState.detailPhoto = {
                            ...detailState.detailPhoto,
                            comments: [newComment, ...(detailState.detailPhoto.comments || [])],
                            comment_count: (detailState.detailPhoto.comment_count || 0) + 1,
                            update_time: nowTs
                        };

                        updatePhotoInListsFn(detailState.detailPhoto.path_key, {
                            comment_count: detailState.detailPhoto.comment_count,
                            update_time: nowTs
                        });
                        commentAdded = true;
                    }
                }

                const currentTitle = detailState.detailPhoto.title || '';
                const currentRating = detailState.detailPhoto.rating || 0;
                const currentTags = Array.isArray(detailState.detailPhoto.tags) ? [...detailState.detailPhoto.tags] : [];
                const original = detailState.originalDetailPhoto;
                if (original
                    && original.title === currentTitle
                    && original.rating === currentRating
                    && U.arraysSameAsSet(original.tags, currentTags)) {
                    showToast(commentAdded ? '保存成功' : '内容未修改', 'success');
                    return true;
                }

                const result = await Api.updatePhoto({
                    path_key: detailState.detailPhoto.path_key,
                    title: detailState.detailPhoto.title,
                    rating: detailState.detailPhoto.rating || 0,
                    tags: detailState.detailPhoto.tags || []
                }, Api.getPassword());

                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return false;
                }
                if (result.ok) {
                    const data = result.data;
                    if (data.meta) {
                        updatePhotoInList(data.meta);
                        detailState.originalDetailPhoto = snapshotDetailPhoto(data.meta);
                        if (data.meta.no_change) {
                            showToast('内容未修改', 'success');
                            return true;
                        }
                    }
                    await loadSummaryCallback();
                    showToast('保存成功', 'success');
                    return true;
                } else {
                    showToast('保存失败', 'error');
                    return false;
                }
            } catch (e) {
                console.error(e);
                showToast('保存失败', 'error');
                return false;
            }
        }

        async function savePhotoAndClose() {
            const success = await savePhoto();
            if (success) {
                closeDetail();
            }
        }

        // ============ 时间编辑 ============
        function initEditCreateTime() {
            if (!detailState.detailPhoto || !detailState.detailPhoto.create_time) {
                editCreateTime.value = '';
                return;
            }
            const d = U.parseTimestamp(detailState.detailPhoto.create_time);
            if (d) {
                const year = d.getFullYear();
                const month = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                const hours = String(d.getHours()).padStart(2, '0');
                const minutes = String(d.getMinutes()).padStart(2, '0');
                editCreateTime.value = `${year}-${month}-${day}T${hours}:${minutes}`;
            } else {
                editCreateTime.value = '';
            }
        }

        function formatEditTime() {
            if (!editCreateTime.value) return '';
            const parts = editCreateTime.value.split('T');
            const datePart = parts[0];
            const timePart = parts[1] || '00:00';
            return `${datePart} ${timePart}`;
        }

        function triggerTimePicker() {
            const hiddenInput = document.querySelector('.time-input-hidden');
            if (hiddenInput) {
                hiddenInput.focus();
                hiddenInput.click();
                if (hiddenInput.showPicker) {
                    try {
                        hiddenInput.showPicker();
                    } catch (e) {}
                }
            }
        }

        async function onTimeChange() {
            const canEdit = (() => {
                if (!detailState.detailPhoto) return false;
                const editCount = detailState.detailPhoto.edit_count || 0;
                return editCount < 2;
            })();
            if (!editCreateTime.value || !canEdit) return;

            if (detailState.detailPhoto && detailState.detailPhoto.create_time) {
                const cur = U.parseTimestamp(detailState.detailPhoto.create_time);
                if (cur) {
                    const parts = editCreateTime.value.split('T');
                    const datePart = parts[0];
                    const timePart = parts[1] || '00:00';
                    const newDate = new Date(`${datePart}T${timePart}:00`);
                    if (!isNaN(newDate.getTime())
                        && cur.getFullYear() === newDate.getFullYear()
                        && cur.getMonth() === newDate.getMonth()
                        && cur.getDate() === newDate.getDate()
                        && cur.getHours() === newDate.getHours()
                        && cur.getMinutes() === newDate.getMinutes()) {
                        showToast('内容未修改', 'success');
                        return;
                    }
                }
            }

            let password = Api.getPassword();
            if (!password) {
                password = await getPassword();
                if (!password) {
                    initEditCreateTime();
                    return;
                }
            }

            try {
                const parts = editCreateTime.value.split('T');
                const datePart = parts[0];
                const timePart = parts[1] || '00:00';
                const newTimeStr = `${datePart} ${timePart}:00`;

                const result = await Api.updatePhoto({
                    path_key: detailState.detailPhoto.path_key,
                    create_time: newTimeStr
                }, password);

                if (result.ok) {
                    const data = result.data;
                    if (data.meta) {
                        detailState.detailPhoto.create_time = data.meta.create_time;
                        detailState.detailPhoto.year = data.meta.year;
                        detailState.detailPhoto.path_key = data.meta.path_key;
                        updatePhotoInList(data.meta);
                        await loadSummaryCallback();
                        await loadPhotosCallback();
                        showToast('时间修改成功', 'success');
                    }
                } else if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误，请重新输入', 'error');
                    initEditCreateTime();
                } else {
                    const err = result.data || {};
                    showToast(err.error || '时间修改失败', 'error');
                    initEditCreateTime();
                }
            } catch (e) {
                console.error(e);
                showToast('时间修改失败', 'error');
                initEditCreateTime();
            }
        }

        // ============ 删除照片 ============
        async function deletePhoto() {
            const confirmed = await showConfirm({
                title: '确认删除',
                message: '确定要删除这张照片吗？此操作无法撤销。',
                confirmText: '确认删除',
                cancelText: '取消',
                danger: true
            });
            if (!confirmed) return;

            if (!detailState.detailPhoto) return;

            try {
                const password = await getPassword();
                if (!password) {
                    return;
                }

                const result = await Api.deletePhoto(detailState.detailPhoto.path_key, password);
                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok) {
                    const deletedPathKey = detailState.detailPhoto.path_key;
                    removePhotoFromList(deletedPathKey);
                    updateYearCountsAfterDelete([deletedPathKey]);
                    closeDetail();
                    await refreshAlbumAfterDelete();
                    showToast('删除成功', 'success');
                } else {
                    showToast('删除失败', 'error');
                }
            } catch (e) {
                console.error(e);
                showToast('删除失败', 'error');
            }
        }

        // ============ 评论 ============
        async function addComment() {
            if (!detailState.detailPhoto || !ui.commentInput.trim()) return;

            try {
                const result = await Api.addComment(detailState.detailPhoto.id, ui.commentInput.trim());
                if (result.ok && result.data?.status === 'ok') {
                    const newComment = {
                        id: result.data.comment_id,
                        text: ui.commentInput.trim(),
                        created_at: new Date().toISOString()
                    };
                    detailState.detailPhoto = {
                        ...detailState.detailPhoto,
                        comments: [newComment, ...(detailState.detailPhoto.comments || [])],
                        comment_count: (detailState.detailPhoto.comment_count || 0) + 1
                    };

                    updatePhotoInListsFn(detailState.detailPhoto.path_key, {
                        comment_count: detailState.detailPhoto.comment_count
                    });
                    showToast('评论添加成功', 'success');
                } else {
                    showToast(result.data?.error || '添加评论失败', 'error');
                }
            } catch (e) {
                console.error('Failed to add comment:', e);
                showToast('添加评论失败', 'error');
            }

            ui.commentInput = '';
            ui.showCommentInput = false;
        }

        async function deleteComment(commentId, idx) {
            if (!detailState.detailPhoto) return;

            const password = await getPassword();
            if (!password) return;

            try {
                const result = await Api.deleteComment(commentId, password);
                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok && result.data?.status === 'ok') {
                    const nowTs = Math.floor(Date.now() / 1000);
                    detailState.detailPhoto = {
                        ...detailState.detailPhoto,
                        comments: (detailState.detailPhoto.comments || []).filter((_, i) => i !== idx),
                        comment_count: Math.max(0, (detailState.detailPhoto.comment_count || 0) - 1),
                        update_time: nowTs
                    };

                    updatePhotoInListsFn(detailState.detailPhoto.path_key, {
                        comment_count: detailState.detailPhoto.comment_count,
                        update_time: nowTs
                    });
                    showToast('评论已删除', 'success');
                } else {
                    showToast(result.data?.error || '删除评论失败', 'error');
                }
            } catch (e) {
                console.error('Failed to delete comment:', e);
                showToast('删除评论失败', 'error');
            }
        }

        // ============ 详情页评分 ============
        async function setDetailRating(val) {
            if (!detailState.detailPhoto) return;
            const oldRating = detailState.detailPhoto.rating || 0;
            if (oldRating === val) return;

            const pathKey = detailState.detailPhoto.path_key;

            const password = Api.getPassword();
            if (!password) {
                const pwd = await getPassword();
                if (!pwd) return;
            }

            try {
                const result = await Api.updatePhoto(
                    { path_key: pathKey, rating: val },
                    Api.getPassword()
                );
                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok) {
                    detailState.detailPhoto.rating = val;
                    if (detailState.originalDetailPhoto) {
                        detailState.originalDetailPhoto.rating = val;
                    }
                    updatePhotoInListsFn(pathKey, { rating: val });
                }
            } catch (e) {
                console.error(e);
                showToast('评分修改失败', 'error');
            }
        }

        // ============ 列表更新辅助函数 ============
        function updatePhotoInList(updatedPhoto) {
            basePhotos.value = basePhotos.value.filter(p => p.id !== updatedPhoto.id);
            basePhotos.value.push(updatedPhoto);
            albumPhotos.value = albumPhotos.value.filter(p => p.id !== updatedPhoto.id);
            albumPhotos.value.push(updatedPhoto);
            refreshComputedCallback();
        }

        function removePhotoFromList(pathKey) {
            removePhotoFromListsFn(pathKey);
        }

        async function refreshAlbumAfterDelete() {
            await loadSummaryCallback();
            // 不调用 loadPhotos() 避免清空列表导致页面闪烁
            // 非年份模式：refreshComputed 已重新计算 yearCounts
            // 年份模式：需要更新 albumYearList 中的 count
        }

        function updateYearCountsAfterDelete(deletedPathKeys) {
            // 统计被删除照片按年份的分布
            const deletedByYear = {};
            for (const pathKey of deletedPathKeys) {
                // pathKey 格式：album_name/year/filename
                const parts = pathKey.split('/');
                if (parts.length === 3) {
                    const year = parts[1];
                    deletedByYear[year] = (deletedByYear[year] || 0) + 1;
                }
            }
            // 更新 albumYearList（年份模式）
            if (albumYearList.value && albumYearList.value.length > 0) {
                albumYearList.value = albumYearList.value.map(y => {
                    const deleted = deletedByYear[String(y.year)] || 0;
                    return { ...y, count: Math.max(0, y.count - deleted) };
                }).filter(y => y.count > 0);
            }
        }

        // ============ 批量删除 ============
        async function batchDelete() {
            if (ui.selectedPhotos.size === 0) return;
            const confirmed = await showConfirm({
                title: '确认删除',
                message: `确定删除 ${ui.selectedPhotos.size} 张照片？此操作无法撤销。`,
                confirmText: '删除',
                cancelText: '取消',
                danger: true
            });
            if (!confirmed) return;

            try {
                const password = await getPassword();
                if (!password) return;

                const result = await Api.batchDelete(Array.from(ui.selectedPhotos), password);
                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok) {
                    const data = result.data;
                    if (data.deleted_path_keys) {
                        removePhotosFromListsFn(data.deleted_path_keys);
                        updateYearCountsAfterDelete(data.deleted_path_keys);
                    }
                    toggleBatchModeCallback();
                    await refreshAlbumAfterDelete();
                    showToast('删除成功', 'success');
                } else {
                    showToast('删除失败', 'error');
                }
            } catch (e) {
                console.error(e);
                showToast('删除失败', 'error');
            }
        }

        return {
            // 详情
            openDetail,
            closeDetail,
            navPhoto,
            handleDetailLeftClick,
            toggleVideoPlay,
            onVideoEnded,
            onVideoKeydown,
            snapshotDetailPhoto,
            restoreVideoProgress,
            saveCurrentVideoProgress,
            // 保存/删除
            savePhoto,
            savePhotoAndClose,
            deletePhoto,
            // 评论
            addComment,
            deleteComment,
            // 评分
            setDetailRating,
            // 时间编辑
            initEditCreateTime,
            formatEditTime,
            triggerTimePicker,
            onTimeChange,
            // 批量删除
            batchDelete,
            // 列表更新
            updatePhotoInList,
            removePhotoFromList,
            refreshAlbumAfterDelete
        };
    }

    window.useDetail = useDetail;
})();
