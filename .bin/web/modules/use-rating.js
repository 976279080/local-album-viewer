/**
 * 评分 composable - 评分弹窗、设置评分
 * 遵循单一职责原则：仅负责评分相关逻辑
 * 依赖：外部传入的 ui/basePhotos/albumPhotos 对象、Api、showToast 等
 */
(function () {
    'use strict';

    function useRating(
        ui, basePhotos, albumPhotos, groupedPhotos, refreshComputedCallback,
        showToast, getPassword, clearPassword
    ) {
        const Api = window.AppApi;

        // ============ 评分 ============
        function openRatingPopup(e, photo) {
            e.stopPropagation();
            ui.ratingTarget = { photo, rect: e.currentTarget.getBoundingClientRect() };
            ui.showRatingPopup = true;
        }

        function closeRatingPopup() {
            ui.showRatingPopup = false;
            ui.ratingTarget = null;
        }

        function handleClickOutsideRating(e) {
            if (ui.showRatingPopup) {
                const popup = document.querySelector('.rating-popup');
                let target = e.target;
                let isHeartClick = false;
                while (target) {
                    if (target.classList && target.classList.contains('rating-heart')) {
                        isHeartClick = true;
                        break;
                    }
                    target = target.parentElement;
                }
                if (popup && !popup.contains(e.target) && !isHeartClick) {
                    closeRatingPopup();
                }
            }

            if (ui.showTagDropdown) {
                const tagInput = e.target.closest('.tag-input-inline');
                if (!tagInput) {
                    ui.showTagDropdown = false;
                }
            }
        }

        function handleMouseLeavePage() {
            if (ui.showRatingPopup) {
                closeRatingPopup();
            }
            if (ui.showTagDropdown) {
                ui.showTagDropdown = false;
            }
        }

        async function setRating(val) {
            if (!ui.ratingTarget) return;
            const { photo } = ui.ratingTarget;
            const oldRating = photo.rating || 0;

            if (oldRating === val) {
                closeRatingPopup();
                return;
            }

            const password = await getPassword();
            if (!password) {
                closeRatingPopup();
                return;
            }

            try {
                const result = await Api.updatePhoto(
                    { path_key: photo.path_key, rating: val },
                    password
                );
                if (Api.isUnauthorized(result)) {
                    clearPassword();
                    showToast('密码错误', 'error');
                    closeRatingPopup();
                    return;
                }
                if (result.ok) {
                    photo.rating = val;
                    const aIdx = albumPhotos.value.findIndex(p => p.path_key === photo.path_key);
                    if (aIdx >= 0) {
                        albumPhotos.value[aIdx].rating = val;
                        albumPhotos.value = [...albumPhotos.value];
                    }
                    const idx = basePhotos.value.findIndex(p => p.path_key === photo.path_key);
                    if (idx >= 0) {
                        const photoObj = basePhotos.value[idx];
                        photoObj.rating = val;
                        const wasCollapsed = oldRating < 0;
                        const isCollapsed = val < 0;

                        if (!wasCollapsed && isCollapsed) {
                            photoObj._lastModified = Date.now();
                            const [moved] = basePhotos.value.splice(idx, 1);
                            basePhotos.value.unshift(moved);
                        } else if (wasCollapsed && !isCollapsed) {
                            photoObj._lastModified = Date.now();
                            const [moved] = basePhotos.value.splice(idx, 1);
                            basePhotos.value.push(moved);
                        }

                        basePhotos.value = [...basePhotos.value];
                        refreshComputedCallback();
                    }
                    if (ui.detailPhoto && ui.detailPhoto.path_key === photo.path_key) {
                        ui.detailPhoto.rating = val;
                        if (ui.originalDetailPhoto) {
                            ui.originalDetailPhoto.rating = val;
                        }
                    }
                }
            } catch (e) {
                console.error(e);
            }
            closeRatingPopup();
        }

        return {
            openRatingPopup,
            closeRatingPopup,
            handleClickOutsideRating,
            handleMouseLeavePage,
            setRating
        };
    }

    window.useRating = useRating;
})();
