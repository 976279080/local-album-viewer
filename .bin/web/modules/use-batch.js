/**
 * 批量选择 composable - 批量选择模式、Shift 多选
 * 遵循单一职责原则：仅负责批量选择相关的状态与逻辑
 * 依赖：外部传入的 ui reactive 对象、照片列表计算属性
 */
(function () {
    'use strict';

    function useBatch(ui, getVisiblePhotos, getGroupedPhotos) {

        function toggleBatchMode() {
            ui.batchMode = !ui.batchMode;
            ui.selectedPhotos.clear();
            ui.lastSelectedPathKey = null;
        }

        function toggleSelect(pathKey, event) {
            if (event && event.shiftKey && ui.lastSelectedPathKey && ui.lastSelectedPathKey !== pathKey) {
                selectPhotosInRange(ui.lastSelectedPathKey, pathKey);
            } else {
                if (ui.selectedPhotos.has(pathKey)) {
                    ui.selectedPhotos.delete(pathKey);
                } else {
                    ui.selectedPhotos.add(pathKey);
                }
                ui.lastSelectedPathKey = pathKey;
            }
        }

        function selectPhotosInRange(startKey, endKey) {
            const allPhotos = [];
            const grouped = getGroupedPhotos();
            const years = Object.keys(grouped).sort((a, b) => b - a);
            for (const year of years) {
                allPhotos.push(...grouped[year].normal);
                allPhotos.push(...grouped[year].collapsed);
            }

            let startIndex = -1;
            let endIndex = -1;

            allPhotos.forEach((photo, index) => {
                if (photo.path_key === startKey) startIndex = index;
                if (photo.path_key === endKey) endIndex = index;
            });

            if (startIndex !== -1 && endIndex !== -1) {
                const min = Math.min(startIndex, endIndex);
                const max = Math.max(startIndex, endIndex);

                for (let i = min; i <= max; i++) {
                    ui.selectedPhotos.add(allPhotos[i].path_key);
                }
            }

            ui.lastSelectedPathKey = endKey;
        }

        function isSelected(pathKey) {
            return ui.selectedPhotos.has(pathKey);
        }

        function getSelectedCount() {
            return ui.selectedPhotos.size;
        }

        function clearSelection() {
            ui.selectedPhotos.clear();
            ui.lastSelectedPathKey = null;
        }

        function getSelectedPathKeys() {
            return Array.from(ui.selectedPhotos);
        }

        return {
            toggleBatchMode,
            toggleSelect,
            isSelected,
            getSelectedCount,
            clearSelection,
            getSelectedPathKeys
        };
    }

    window.useBatch = useBatch;
})();
