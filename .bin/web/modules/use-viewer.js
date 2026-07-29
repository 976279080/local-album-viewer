/**
 * 大图查看器 composable - 缩放/拖拽/键盘/复制
 * 遵循单一职责原则：仅负责大图查看器交互
 * 依赖：Vue（无需直接依赖，操作外部传入的 ui 对象）
 *
 * 设计说明：为保持 index.html 模板兼容，直接操作传入的 ui 对象字段：
 *   showLargeViewer / viewerScale / viewerPosX / viewerPosY /
 *   viewerIsDragging / viewerDragStart / viewerFitMode / viewerFitScale
 */
(function () {
    'use strict';

    /**
     * @param {object} ui 主应用的 ui reactive 对象
     * @param {function} showToast 通知函数（来自 useNotifications）
     * @returns 大图查看器相关方法
     */
    function useViewer(ui, showToast) {

        /** 计算适应窗口的缩放比例 */
        function computeFitScale() {
            const img = document.querySelector('.preview-img');
            const container = document.querySelector('.viewer-content');
            if (!img || !container) return 1;
            const imgWidth = img.naturalWidth || img.offsetWidth;
            const imgHeight = img.naturalHeight || img.offsetHeight;
            const containerWidth = container.clientWidth - 40;
            const containerHeight = container.clientHeight - 60;
            if (!imgWidth || !imgHeight) return 1;
            const scaleX = containerWidth / imgWidth;
            const scaleY = containerHeight / imgHeight;
            return Math.min(scaleX, scaleY, 1);
        }

        function openLargeViewer(detailPhoto, isVideoFn) {
            if (!detailPhoto || isVideoFn(detailPhoto)) return;
            ui.showLargeViewer = true;
            ui.viewerScale = 1;
            ui.viewerPosX = 0;
            ui.viewerPosY = 0;
            ui.viewerFitMode = true;
            setTimeout(() => {
                const img = document.querySelector('.preview-img');
                if (img) {
                    if (img.complete && img.naturalWidth) {
                        ui.viewerFitScale = computeFitScale();
                    } else {
                        img.onload = () => {
                            ui.viewerFitScale = computeFitScale();
                        };
                    }
                }
            }, 100);
        }

        function closeLargeViewer() {
            ui.showLargeViewer = false;
        }

        function viewerZoomIn() {
            if (ui.viewerFitMode) {
                ui.viewerScale = ui.viewerFitScale;
                ui.viewerFitMode = false;
            }
            ui.viewerScale = Math.min(5, ui.viewerScale + 0.2);
        }

        function viewerZoomOut() {
            if (ui.viewerFitMode) {
                ui.viewerScale = ui.viewerFitScale;
                ui.viewerFitMode = false;
            }
            ui.viewerScale = Math.max(0.1, ui.viewerScale - 0.2);
        }

        function viewerFit() {
            ui.viewerScale = 1;
            ui.viewerPosX = 0;
            ui.viewerPosY = 0;
            ui.viewerFitMode = true;
            ui.viewerFitScale = computeFitScale();
        }

        function viewerOrigin() {
            ui.viewerScale = 1;
            ui.viewerPosX = 0;
            ui.viewerPosY = 0;
            ui.viewerFitMode = false;
            ui.viewerFitScale = 1;
        }

        function startViewerDrag(e) {
            e.preventDefault();
            ui.viewerIsDragging = true;
            ui.viewerDragStart = { x: e.clientX - ui.viewerPosX, y: e.clientY - ui.viewerPosY };
        }

        function handleViewerMouseMove(e) {
            if (!ui.viewerIsDragging) return;
            ui.viewerPosX = e.clientX - ui.viewerDragStart.x;
            ui.viewerPosY = e.clientY - ui.viewerDragStart.y;
        }

        function handleViewerMouseUp() {
            ui.viewerIsDragging = false;
        }

        function onViewerWheel(e) {
            const img = e.currentTarget.querySelector('.preview-img');
            if (!img) return;
            const rect = img.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            if (ui.viewerFitMode) {
                ui.viewerScale = ui.viewerFitScale;
                ui.viewerFitMode = false;
            }
            const oldScale = ui.viewerScale;
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            ui.viewerScale = Math.max(0.1, Math.min(5, ui.viewerScale + delta));
            ui.viewerPosX += mouseX * (1 - ui.viewerScale / oldScale);
            ui.viewerPosY += mouseY * (1 - ui.viewerScale / oldScale);
        }

        function onViewerDblClick(e) {
            e.preventDefault();
            if (ui.viewerFitMode) {
                ui.viewerScale = ui.viewerFitScale;
                ui.viewerFitMode = false;
            }
            if (ui.viewerScale === 1) {
                ui.viewerScale = 2;
                const rect = e.currentTarget.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;
                ui.viewerPosX -= mouseX;
                ui.viewerPosY -= mouseY;
            } else {
                ui.viewerScale = 1;
                ui.viewerPosX = 0;
                ui.viewerPosY = 0;
            }
        }

        async function viewerCopy() {
            try {
                const img = document.querySelector('.preview-img');
                if (!img) return;
                const res = await fetch(img.src);
                const blob = await res.blob();
                await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
                showToast('图片已复制', 'success');
            } catch (err) {
                showToast('复制失败，请手动复制', 'error');
            }
        }

        function handleViewerKeyDown(e) {
            if (!ui.showLargeViewer) return;
            if (e.key === 'Escape') {
                closeLargeViewer();
            }
        }

        function handleViewerResize() {
            if (ui.showLargeViewer && ui.viewerFitMode) {
                ui.viewerFitScale = computeFitScale();
            }
        }

        return {
            openLargeViewer, closeLargeViewer,
            viewerZoomIn, viewerZoomOut, viewerFit, viewerOrigin,
            startViewerDrag, handleViewerMouseMove, handleViewerMouseUp,
            onViewerWheel, onViewerDblClick, viewerCopy,
            handleViewerKeyDown, handleViewerResize
        };
    }

    window.useViewer = useViewer;
})();
