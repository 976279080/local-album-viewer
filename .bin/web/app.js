/**
 * 相册应用主入口
 * 依赖以下模块（需在 app.js 之前加载）：
 *   - vue.global.min.js
 *   - config.js
 *   - modules/constants.js
 *   - modules/utils.js
 *   - modules/api.js
 *   - modules/use-notifications.js
 *   - modules/use-confirm.js
 *   - modules/use-password.js
 *   - modules/use-license.js
 *   - modules/use-viewer.js
 *   - modules/use-batch.js
 *   - modules/use-photos.js
 *   - modules/use-filter.js
 *   - modules/use-rating.js
 *   - modules/use-tags.js
 *   - modules/use-detail.js
 */
const { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick } = Vue;

const app = createApp({
    setup() {
        // ============ 模块引入 ============
        const { notifications, showToast, initGlobalErrorHandling } = useNotifications();
        const { confirmState, showConfirm, handleConfirm } = useConfirm();
        const { getPassword, clearPassword: clearCachedPassword, hasPassword } = usePassword();
        const { getLicenseStatus, activateLicense, clearLicense, promptLicenseAndPassword } = useLicense();

        const C = window.AppConstants;
        const U = window.AppUtils;
        const Api = window.AppApi;

        // ============ 状态定义 ============
        const albumPhotos = ref([]);
        const basePhotos = ref([]);
        const summary = ref({ members: {}, tags: {} });
        const albumOrder = ref([]);
        const hasLoaded = ref(false);
        const hasAlbumData = ref(false); // 当前相册的照片数据是否已加载（API 返回后才为 true）
        const contentKey = ref(0);
        const useYearMode = ref(false);
        const albumYearList = ref([]);

        const filter = reactive({
            album: '',
            year: '',
            type: 'all',
            tag: '',
            rating: ''
        });

        const ui = reactive({
            batchMode: false,
            selectedPhotos: new Set(),
            lastSelectedPathKey: null,
            collapsedYears: [],
            showRatingPopup: false,
            ratingTarget: null,
            commentInput: '',
            showCommentInput: false,
            batchTags: [],
            showBatchTagModal: false,
            batchTagInput: '',
            showBatchTagDropdown: false,
            showDeleteConfirm: false,
            showTagDropdown: false,
            showLargeViewer: false,
            viewerScale: 1,
            viewerPosX: 0,
            viewerPosY: 0,
            viewerIsDragging: false,
            viewerDragStart: { x: 0, y: 0 },
            viewerFitMode: true,
            viewerFitScale: 1
        });

        const detailState = reactive({
            currentPhotoIndex: -1,
            detailPhoto: null,
            showDetail: false,
            fileExists: true,
            originalDetailPhoto: null
        });

        const tagInputValue = ref('');
        const editCreateTime = ref('');

        const photoSize = ref('normal');
        const sortBy = reactive({});
        const sortOrder = reactive({});
        const openDropdown = ref(null);
        const openSortDropdown = ref(null);

        const ratingLevels = C.RATING_LEVELS;

        const groupedPhotos = ref({});
        const visibleYears = ref([]);
        const displayedGroupedPhotos = ref({});
        const yearCounts = ref({});
        const availableTags = ref({});

        const renderState = reactive({
            count: C.INITIAL_RENDER_COUNT,
            hasMore: false,
            total: 0,
            rendered: 0
        });

        // ============ 验证函数 ============
        function validateText(text, fieldName) {
            if (!text) return true;
            if (U.hasIllegalChars(text)) {
                showToast(`${fieldName}不能包含特殊字符：${C.ILLEGAL_CHARS_STR}`, 'error');
                return false;
            }
            return true;
        }

        function validateComment(text, fieldName) {
            if (!text) return true;
            if (U.hasCommentIllegalChars(text)) {
                showToast(`${fieldName}不能包含特殊字符：${C.COMMENT_ILLEGAL_CHARS_STR}`, 'error');
                return false;
            }
            return true;
        }

        // ============ composables 组合 ============

        const {
            filteredPhotos,
            visiblePhotos,
            yearDropdownData,
            yearAllCount,
            canEditTime: canEditTimeBase,
            computeBasePhotos,
            computeGroupedPhotos,
            computeYearCounts,
            computeAvailableTags,
            refreshComputed,
            loadSummary,
            applyPhotosData,
            resetRenderCount,
            increaseRenderCount,
            updatePhotoInLists,
            updatePhotoInListsBatch,
            removePhotoFromLists,
            removePhotosFromLists,
            displayedYears
        } = usePhotos(
            albumPhotos, basePhotos, summary, albumOrder,
            filter, ui, photoSize, sortBy, sortOrder,
            groupedPhotos, visibleYears, displayedGroupedPhotos,
            yearCounts, availableTags, useYearMode, albumYearList,
            contentKey, renderState
        );

        const {
            toggleDropdown,
            closeAllDropdowns,
            toggleCollapsed,
            isCollapsedVisible,
            changeSort
        } = useFilter(
            filter, ui, openDropdown, openSortDropdown,
            sortBy, sortOrder,
            refreshComputed,
            groupedPhotos
        );

        function setFilter(name, value) {
            filter[name] = value;
            openDropdown.value = null;
            if (name === 'album') {
                filter.year = null;
                filter.tag = '';
                if (filter.album) {
                    window.location.hash = `album=${encodeURIComponent(filter.album)}`;
                }
                // 始终清空旧数据（不同相册的数据不应继续显示）
                albumPhotos.value = [];
                basePhotos.value = [];
                hasAlbumData.value = false; // 标记数据未加载，避免闪现"暂无照片"
                resetRenderCount();
                nextTick(() => {
                    loadPhotos();
                });
            } else if (name === 'year') {
                if (useYearMode.value) {
                    // 始终清空旧数据（不同年份的数据不应继续显示）
                    albumPhotos.value = [];
                    basePhotos.value = [];
                    hasAlbumData.value = false; // 标记数据未加载，避免闪现"暂无照片"
                    resetRenderCount();
                    loadPhotos();
                } else {
                    resetRenderCount();
                    computeBasePhotos();
                    refreshComputed();
                    ui.collapsedYears = Object.keys(groupedPhotos.value);
                    Object.keys(groupedPhotos.value).forEach(year => {
                        if (groupedPhotos.value[year] && groupedPhotos.value[year].normal.length === 0 && groupedPhotos.value[year].collapsed.length > 0) {
                            const idx = ui.collapsedYears.indexOf(year);
                            if (idx !== -1) {
                                ui.collapsedYears.splice(idx, 1);
                            }
                        }
                    });
                }
            } else {
                // 切换标签/类型/评分：前端筛选，不涉及 API
                resetRenderCount();
                refreshComputed();
                ui.collapsedYears = Object.keys(groupedPhotos.value);
                Object.keys(groupedPhotos.value).forEach(year => {
                    if (groupedPhotos.value[year] && groupedPhotos.value[year].normal.length === 0 && groupedPhotos.value[year].collapsed.length > 0) {
                        const idx = ui.collapsedYears.indexOf(year);
                        if (idx !== -1) {
                            ui.collapsedYears.splice(idx, 1);
                        }
                    }
                });
            }
        }

        const {
            openRatingPopup,
            closeRatingPopup,
            handleClickOutsideRating,
            handleMouseLeavePage,
            setRating
        } = useRating(
            ui, basePhotos, albumPhotos, groupedPhotos, refreshComputed,
            showToast, getPassword, clearCachedPassword
        );

        const {
            filteredTags,
            batchFilteredTags,
            addTag,
            addDetailTag,
            addExistingTag,
            addNewTag,
            selectTag,
            createAndAddTag,
            removeTag,
            showBatchTagModal,
            closeBatchTagModal,
            addBatchTag,
            selectBatchTag,
            removeBatchTag,
            confirmBatchTag,
            batchClearTags,
            getAlbumName,
            getAlbumColor,
            getTagColor
        } = useTags(
            ui, detailState, tagInputValue, basePhotos, albumPhotos, availableTags, summary,
            refreshComputed, loadSummary, computeAvailableTags,
            () => { ui.batchMode = !ui.batchMode; ui.selectedPhotos.clear(); ui.lastSelectedPathKey = null; },
            showToast, getPassword, clearCachedPassword, validateText, showConfirm,
            updatePhotoInListsBatch
        );

        const {
            openDetail,
            closeDetail,
            navPhoto,
            handleDetailLeftClick,
            toggleVideoPlay,
            onVideoEnded,
            onVideoKeydown,
            restoreVideoProgress,
            saveCurrentVideoProgress,
            savePhoto,
            savePhotoAndClose,
            deletePhoto,
            addComment,
            deleteComment,
            initEditCreateTime,
            formatEditTime,
            triggerTimePicker,
            onTimeChange,
            batchDelete,
            updatePhotoInList,
            removePhotoFromList
        } = useDetail(
            ui, detailState, basePhotos, albumPhotos, visiblePhotos, editCreateTime, tagInputValue, summary,
            refreshComputed, loadSummary, loadPhotos,
            showToast, getPassword, clearCachedPassword, showConfirm,
            validateText, validateComment,
            () => { ui.batchMode = !ui.batchMode; ui.selectedPhotos.clear(); ui.lastSelectedPathKey = null; },
            albumYearList,
            openDropdown,
            updatePhotoInLists, removePhotoFromLists, removePhotosFromLists
        );

        const {
            toggleBatchMode: toggleBatchModeBase,
            toggleSelect,
            isSelected,
            getSelectedCount,
            clearSelection,
            getSelectedPathKeys
        } = useBatch(
            ui,
            () => visiblePhotos.value,
            () => groupedPhotos.value
        );

        function toggleBatchMode() {
            toggleBatchModeBase();
        }

        const editMode = ref(hasPassword());

        const canEditTime = computed(() => editMode.value && canEditTimeBase.value);

        async function toggleEditMode() {
            if (editMode.value) {
                // 退出编辑模式
                editMode.value = false;
                clearCachedPassword();
                if (ui.batchMode) toggleBatchModeBase();
                if (detailState.showDetail) {
                    detailState.showDetail = false;
                    detailState.detailPhoto = null;
                }
                showToast('已退出编辑模式', 'info');
                return;
            }

            // 1. 获取授权状态
            const status = await getLicenseStatus();

            // 2. 判断是否需要授权码
            // first_upload_time === null 视为免费期内（新用户还没上传过）
            const needLicense = !status.has_license
                && status.first_upload_time !== null
                && !status.in_free_trial;

            let password;
            if (needLicense) {
                // 3. 需要授权码：弹组合框（内部验证授权码和密码）
                const result = await promptLicenseAndPassword();
                if (!result) return; // 用户取消

                // 授权码已在弹窗中激活，密码已验证
                password = result.password;
                sessionStorage.setItem(C.PASSWORD_STORAGE_KEY, password);

                // 授权码即将过期提示（仅 <=7 天提醒），其余直接显示授权成功
                const newStatus = await getLicenseStatus();
                if (newStatus.has_license && newStatus.remaining_days > 0 && newStatus.remaining_days <= 7) {
                    showToast(`授权成功，剩余 ${newStatus.remaining_days} 天即将到期，请及时续费`, 'warning');
                } else {
                    showToast('授权成功', 'success');
                }
            } else {
                // 4. 不需要授权码：弹密码框（内部验证密码）
                password = await getPassword();
                if (!password) return;

                // 授权码即将过期提示
                if (status.has_license && status.remaining_days > 0 && status.remaining_days <= 30) {
                    setTimeout(() => {
                        showToast(`授权码将在 ${status.remaining_days} 天后过期，请及时续费`, 'warning');
                    }, 500);
                }
            }

            // 5. 进入编辑模式
            editMode.value = true;
            if (!needLicense) {
                showToast('已进入编辑模式', 'success');
            }
        }

        // ============ 大图查看器 ============
        const {
            openLargeViewer, closeLargeViewer,
            viewerZoomIn, viewerZoomOut, viewerFit, viewerOrigin,
            startViewerDrag, handleViewerMouseMove, handleViewerMouseUp,
            onViewerWheel, onViewerDblClick, viewerCopy,
            handleViewerKeyDown, handleViewerResize
        } = useViewer(ui, showToast);

        // ============ 首页初始化 ============
        async function loadHomeInit(retries = C.RETRY_HOME_INIT) {
            try {
                const hashParams = new URLSearchParams(window.location.hash.slice(1));
                const hashAlbum = hashParams.get('album');

                const albumParam = filter.album || hashAlbum;
                const data = await Api.fetchHomeInit(albumParam);

                if (data.status === 'loading') {
                    if (retries > 0) {
                        await new Promise(resolve => setTimeout(resolve, C.RETRY_INTERVAL));
                        return await loadHomeInit(retries - 1);
                    }
                    console.warn('首页初始化超时，降级为分步加载');
                    await loadSummary();
                    await loadPhotos();
                    return;
                }

                summary.value = data.summary || {};
                albumOrder.value = (data.summary && data.summary.album_order) || Object.keys(summary.value.members || {});
                if (!filter.album && summary.value.members && Object.keys(summary.value.members).length > 0) {
                    filter.album = hashAlbum || (data.album_years && data.album_years.album_id) || albumOrder.value[0];
                }

                if (data.album_years || data.photos) {
                    if (data.album_years && data.album_years.selected_year) {
                        filter.year = data.album_years.selected_year;
                    }
                    applyPhotosData(data.photos, data.album_years);
                    hasAlbumData.value = true; // 数据加载完成，允许显示"暂无照片"
                }
            } catch (e) {
                console.error('首页初始化失败，降级为分步加载:', e);
                await loadSummary();
                await loadPhotos();
            }
        }

        async function loadPhotos() {
            try {
                if (!filter.album) return;

                const data = await Api.fetchAlbumInit(filter.album, filter.year);

                if (data.status === 'ok') {
                    applyPhotosData(data.photos, data.album_years);
                    hasAlbumData.value = true; // 数据加载完成，允许显示"暂无照片"
                }
            } catch (e) {
                console.error(e);
            } finally {
                hasLoaded.value = true;
            }
        }

        // ============ 生命周期 ============

        // 滚动监听：接近底部时追加渲染更多
        let scrollTimeout = null;
        let scrollContainer = null;
        let isScrollHandlerBound = false;
        function handleScroll() {
            if (!renderState.hasMore) return;
            if (!scrollContainer) return;

            if (scrollTimeout) clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                scrollTimeout = null;
                if (!renderState.hasMore) return;

                const scrollTop = scrollContainer.scrollTop;
                const clientHeight = scrollContainer.clientHeight;
                const scrollHeight = scrollContainer.scrollHeight;

                if (scrollTop + clientHeight >= scrollHeight - 800) {
                    increaseRenderCount();
                }
            }, 80);
        }

        function bindScrollListener() {
            if (isScrollHandlerBound) return;
            if (!scrollContainer) return;
            scrollContainer.addEventListener('scroll', handleScroll, { passive: true });
            isScrollHandlerBound = true;
        }

        onMounted(async () => {
            initGlobalErrorHandling();

            scrollContainer = document.getElementById('app');
            bindScrollListener();

            // 合并请求：一次获取 summary + album-years + photos（减少 1 次 HTTP 往返）
            // loadHomeInit 内部读取 URL hash 中的 album 参数，并处理降级：
            //   - status=loading → 重试，超时则降级为分步加载
            //   - 请求失败 → 降级为 loadSummary + loadPhotos
            await loadHomeInit();

            hasLoaded.value = true;
            document.addEventListener('click', handleClickOutsideRating);
            document.addEventListener('mouseleave', handleMouseLeavePage);
            document.addEventListener('mousemove', handleViewerMouseMove);
            document.addEventListener('mouseup', handleViewerMouseUp);
            document.addEventListener('keydown', handleViewerKeyDown);
            window.addEventListener('resize', handleViewerResize);
        });

        onUnmounted(() => {
            document.removeEventListener('click', handleClickOutsideRating);
            document.removeEventListener('mouseleave', handleMouseLeavePage);
            document.removeEventListener('mousemove', handleViewerMouseMove);
            document.removeEventListener('mouseup', handleViewerMouseUp);
            document.removeEventListener('keydown', handleViewerKeyDown);
            window.removeEventListener('resize', handleViewerResize);
            if (scrollContainer) {
                scrollContainer.removeEventListener('scroll', handleScroll);
            }
        });

        // ============ 暴露给模板 ============
        return {
            // 状态
            photos: basePhotos,
            albumPhotos,
            summary,
            albumOrder,
            filter,
            ui,
            photoSize,
            sortBy,
            sortOrder,
            openDropdown,
            openSortDropdown,
            tagInputValue,
            ratingLevels,
            editCreateTime,
            editMode,
            // 计算属性
            filteredPhotos,
            groupedPhotos,
            displayedGroupedPhotos,
            visibleYears,
            displayedYears,
            visiblePhotos,
            filteredTags,
            batchFilteredTags,
            yearCounts,
            availableTags,
            useYearMode,
            albumYearList,
            yearDropdownData,
            yearAllCount,
            canEditTime,
            // 加载状态
            hasLoaded,
            hasAlbumData,
            contentKey,
            renderState,
            // 数据加载
            loadPhotos,
            increaseRenderCount,
            // 筛选
            toggleDropdown,
            setFilter,
            toggleCollapsed,
            isCollapsedVisible,
            closeAllDropdowns,
            // 批量
            toggleBatchMode,
            toggleSelect,
            isSelected,
            // 详情
            openDetail,
            closeDetail,
            navPhoto,
            handleDetailLeftClick,
            toggleVideoPlay,
            onVideoEnded,
            onVideoKeydown,
            restoreVideoProgress,
            saveCurrentVideoProgress,
            // 评分
            openRatingPopup,
            closeRatingPopup,
            setRating,
            // 标签
            addTag,
            addDetailTag,
            addExistingTag,
            addNewTag,
            selectTag,
            createAndAddTag,
            removeTag,
            // 保存/删除
            savePhoto,
            savePhotoAndClose,
            deletePhoto,
            // 评论
            addComment,
            deleteComment,
            // 批量操作
            showBatchTagModal,
            closeBatchTagModal,
            addBatchTag,
            selectBatchTag,
            removeBatchTag,
            confirmBatchTag,
            batchDelete,
            batchClearTags,
            // 排序
            changeSort,
            // 编辑模式
            toggleEditMode,
            // 详情状态
            detailState,
            // 工具函数
            isVideo: (photo) => photo?.file_type === 'video',
            handleVideoThumbnailError: U.handleVideoThumbnailError,
            handleImageError: U.handleImageError,
            handleDetailImageError: () => { detailState.fileExists = false; },
            handleImageLoad: U.handleImageLoad,
            formatDate: U.formatDate,
            formatDateTime: U.formatDateTime,
            formatCommentDate: U.formatCommentDate,
            isModifiedToday: U.isModifiedToday,
            formatFileSize: U.formatFileSize,
            encodePathKey: U.encodePathKey,
            // 心形SVG
            getHeartSvg: C.getHeartSvg,
            // 颜色/名称
            getAlbumName,
            getAlbumColor,
            getTagColor,
            // 大图查看器
            openLargeViewer,
            closeLargeViewer,
            viewerZoomIn,
            viewerZoomOut,
            viewerFit,
            viewerOrigin,
            startViewerDrag,
            onViewerWheel,
            onViewerDblClick,
            viewerCopy,
            // 时间编辑
            onTimeChange,
            formatEditTime,
            triggerTimePicker,
            // 通知与确认
            notifications,
            confirmState,
            handleConfirm
        };
    }
});

window.__vm = app.mount("#app");

// ---------- 首次进入引导遮罩（首页） ----------
(function () {
    function showGuide() {
        // 等待 DOM 渲染完成后定位按钮
        setTimeout(function () {
            var btn = document.querySelector('.btn-edit-mode');
            if (!btn) { return; }

            var rect = btn.getBoundingClientRect();
            var old = document.getElementById('spotlightGuide');
            if (old) old.remove();

            var btnStyle = window.getComputedStyle(btn);
            var spotRadius = btnStyle.borderRadius || '8px';

            // 核心：用 box-shadow 实现真正的圆角矩形镂空遮罩
            // 透明 div + 向外扩散的黑色 box-shadow = 完美的聚光灯效果
            var spotlight = document.createElement('div');
            spotlight.id = 'spotlightGuide';
            spotlight.style.cssText = [
                'position:fixed',
                'left:' + rect.left + 'px',
                'top:' + rect.top + 'px',
                'width:' + rect.width + 'px',
                'height:' + rect.height + 'px',
                'border-radius:' + spotRadius,
                'box-shadow:0 0 0 9999px rgba(0,0,0,0.95)',
                'z-index:9999',
                'pointer-events:auto',
            ].join(';');

            // 引导提示气泡（居中显示在按钮下方）
            var tipW = 380;
            var tipH = 220;
            var tipLeft = Math.max(16, (window.innerWidth - tipW) / 2);
            var belowSpace = window.innerHeight - (rect.top + rect.height);
            var tipTop = (belowSpace > tipH + 24)
                ? (rect.top + rect.height + 16)
                : Math.max(16, rect.top - tipH - 16);

            var tip = document.createElement('div');
            tip.style.cssText = 'position:fixed;z-index:10001;' +
                'left:' + tipLeft + 'px;' +
                'top:' + tipTop + 'px;' +
                'width:' + tipW + 'px;' +
                'background:#fff;border-radius:12px;padding:24px 28px;' +
                'box-shadow:0 8px 32px rgba(0,0,0,0.25);' +
                'box-sizing:border-box;';
            tip.innerHTML =
                '<div style="font-size:18px;font-weight:600;color:#1e293b;margin-bottom:12px;">欢迎使用本地相册</div>' +
                '<div style="font-size:14px;color:#64748b;line-height:1.7;margin-bottom:16px;">' +
                    '点击上方的「编辑模式」按钮进入编辑状态，<br>' +
                    '然后点击「上传」按钮上传照片。' +
                '</div>' +
                '<div style="font-size:14px;color:#64748b;line-height:1.7;margin-bottom:16px;">' +
                    '上传密码：<strong style="color:#667eea;font-size:16px;">111222</strong>' +
                '</div>' +
                '<button id="spotlightCloseBtn" style="' +
                    'background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);' +
                    'color:#fff;border:none;padding:10px 28px;border-radius:8px;' +
                    'font-size:15px;cursor:pointer;width:100%;font-weight:500;' +
                '">知道了</button>';

            // 组装：先加聚光灯（带 box-shadow 的镂空层），再加提示气泡
            document.body.appendChild(spotlight);
            document.body.appendChild(tip);

            function closeGuide() {
                spotlight.remove();
                tip.remove();
            }

            // 点击镂空区域外的黑色遮罩关闭
            spotlight.addEventListener('click', function (e) {
                if (e.target === spotlight) {
                    closeGuide();
                }
            });
            // "知道了"按钮关闭
            tip.querySelector('#spotlightCloseBtn').onclick = function () {
                closeGuide();
            };
            // ESC 关闭
            document.addEventListener('keydown', function onKey(e) {
                if (e.key === 'Escape') {
                    closeGuide();
                    document.removeEventListener('keydown', onKey);
                }
            });
        }, 800);
    }

    // 检查是否需要显示引导
    fetch('/api/ui-config').then(function (r) { return r.json(); }).then(function (cfg) {
        if (cfg.force_first_time_guide) {
            showGuide();
        } else if (!cfg.has_uploaded) {
            // 没有上传过，显示引导
            showGuide();
        }
    }).catch(function () { /* ignore */ });
})();
