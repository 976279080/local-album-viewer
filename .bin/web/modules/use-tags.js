/**
 * 标签 composable - 标签编辑、批量标签
 * 遵循单一职责原则：仅负责标签相关逻辑
 * 依赖：外部传入的 ui/basePhotos/albumPhotos 对象、Api、showToast 等
 */
(function () {
    'use strict';

    function useTags(
        ui, detailState, tagInputValue, basePhotos, albumPhotos, availableTags, summary,
        refreshComputedCallback, loadSummaryCallback, computeAvailableTagsCallback,
        toggleBatchModeCallback, showToast, getPassword, clearCachedPassword,
        validateText, showConfirm,
        updatePhotoInListsBatchFn
    ) {
        const U = window.AppUtils;
        const Api = window.AppApi;

        // ============ 标签筛选计算属性 ============
        const filteredTags = Vue.computed(() => {
            const input = tagInputValue.value?.trim().toLowerCase() || '';
            const tags = Object.keys(availableTags.value);
            if (!input) return tags;
            return tags.filter(tag => tag.toLowerCase().includes(input));
        });

        const batchFilteredTags = Vue.computed(() => {
            const input = ui.batchTagInput?.trim().toLowerCase() || '';
            const tags = Object.keys(availableTags.value);
            if (!input) return tags;
            return tags.filter(tag => tag.toLowerCase().includes(input));
        });

        // ============ 标签编辑 ============
        function addTag(tag) {
            if (!detailState.detailPhoto) return;
            if (!detailState.detailPhoto.tags) detailState.detailPhoto.tags = [];
            if (detailState.detailPhoto.tags.includes(tag)) return;

            detailState.detailPhoto.tags.push(tag);
        }

        function addDetailTag() {
            const tag = tagInputValue.value.trim();
            if (tag) {
                if (!validateText(tag, '标签')) return;
                addTag(tag);
                tagInputValue.value = '';
                ui.showTagDropdown = false;
            }
        }

        function addExistingTag(tag) {
            addTag(tag);
            tagInputValue.value = '';
            ui.showTagDropdown = false;
        }

        function addNewTag(tag) {
            addTag(tag);
            tagInputValue.value = '';
            ui.showTagDropdown = false;
        }

        function selectTag(tag) {
            addExistingTag(tag);
        }

        function createAndAddTag(tag) {
            addNewTag(tag);
        }

        function removeTag(tag) {
            if (!detailState.detailPhoto) return;
            detailState.detailPhoto.tags = detailState.detailPhoto.tags.filter(t => t !== tag);
        }

        // ============ 批量标签 ============
        function showBatchTagModal() {
            ui.batchTags = [];
            ui.batchTagInput = '';
            ui.showBatchTagDropdown = false;
            ui.showBatchTagModal = true;
        }

        function closeBatchTagModal() {
            ui.showBatchTagModal = false;
            ui.showBatchTagDropdown = false;
        }

        function addBatchTag(tag) {
            if (!ui.batchTags.includes(tag)) {
                ui.batchTags.push(tag);
            }
            ui.batchTagInput = '';
            ui.showBatchTagDropdown = false;
        }

        function selectBatchTag(tag) {
            if (!ui.batchTags.includes(tag)) {
                ui.batchTags.push(tag);
            }
            ui.batchTagInput = '';
            ui.showBatchTagDropdown = false;
        }

        function removeBatchTag(tag) {
            ui.batchTags = ui.batchTags.filter(t => t !== tag);
        }

        async function confirmBatchTag() {
            if (ui.batchTags.length === 0) return;
            closeBatchTagModal();
            const password = await getPassword();
            if (!password) return;
            try {
                const result = await Api.batchTag(
                    Array.from(ui.selectedPhotos),
                    ui.batchTags,
                    password
                );
                if (Api.isUnauthorized(result)) {
                    clearCachedPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok) {
                    const data = result.data;
                    if (data.updated) {
                        const updates = data.updated.map(updated => {
                            const patch = { tags: updated.tags };
                            if (updated.update_time != null) {
                                patch.update_time = updated.update_time;
                            }
                            return { path_key: updated.path_key, patch };
                        });
                        updatePhotoInListsBatchFn(updates);
                    }
                    await loadSummaryCallback();
                    computeAvailableTagsCallback();
                    toggleBatchModeCallback();
                    showToast('标签已添加', 'success');
                } else {
                    showToast('操作失败', 'error');
                }
            } catch (e) {
                console.error(e);
                showToast('操作失败', 'error');
            }
        }

        async function batchClearTags() {
            if (ui.selectedPhotos.size === 0) return;
            const confirmed = await showConfirm({
                title: '确认清空标签',
                message: '确定清空选中照片的所有标签？',
                confirmText: '清空',
                cancelText: '取消'
            });
            if (!confirmed) return;

            const password = await getPassword();
            if (!password) return;

            try {
                const result = await Api.batchClearTags(Array.from(ui.selectedPhotos), password);
                if (Api.isUnauthorized(result)) {
                    clearCachedPassword();
                    showToast('密码错误', 'error');
                    return;
                }
                if (result.ok) {
                    const data = result.data;
                    if (data.updated) {
                        const updates = data.updated.map(updated => {
                            const patch = { tags: updated.tags };
                            if (updated.update_time != null) {
                                patch.update_time = updated.update_time;
                            }
                            return { path_key: updated.path_key, patch };
                        });
                        updatePhotoInListsBatchFn(updates);
                    }
                    toggleBatchModeCallback();
                    setTimeout(() => showToast('标签已清空', 'success'), 200);
                } else {
                    setTimeout(() => showToast('操作失败', 'error'), 200);
                }
            } catch (e) {
                console.error(e);
                setTimeout(() => showToast('操作失败', 'error'), 200);
            }
        }

        // ============ 颜色/名称辅助 ============
        function getAlbumName(albumId) {
            return summary.value.members?.[albumId]?.name || albumId;
        }

        function getAlbumColor(albumId) {
            return summary.value.members?.[albumId]?.color || '#666';
        }

        function getTagColor(tag) {
            return summary.value.tags?.[tag]?.color || availableTags.value[tag]?.color || U.getRandomTagColor(tag);
        }

        return {
            // 计算属性
            filteredTags,
            batchFilteredTags,
            // 标签编辑
            addTag,
            addDetailTag,
            addExistingTag,
            addNewTag,
            selectTag,
            createAndAddTag,
            removeTag,
            // 批量标签
            showBatchTagModal,
            closeBatchTagModal,
            addBatchTag,
            selectBatchTag,
            removeBatchTag,
            confirmBatchTag,
            batchClearTags,
            // 颜色/名称
            getAlbumName,
            getAlbumColor,
            getTagColor
        };
    }

    window.useTags = useTags;
})();
