/**
 * 照片数据 composable - 照片加载、筛选、分组计算
 * 遵循单一职责原则：仅负责照片数据管理与计算
 * 依赖：外部传入的 ref/reactive 对象、Api、AppConstants、AppUtils
 */
(function () {
    'use strict';

    function usePhotos(
        albumPhotos, basePhotos, summary, albumOrder,
        filter, ui, photoSize, sortBy, sortOrder,
        groupedPhotos, visibleYears, displayedGroupedPhotos,
        yearCounts, availableTags, useYearMode, albumYearList,
        contentKey, renderState
    ) {
        const C = window.AppConstants;
        const U = window.AppUtils;
        const Api = window.AppApi;

        // ============ 计算属性 ============
        const filteredPhotos = Vue.computed(() => {
            let result = basePhotos.value.slice();

            if (filter.type && filter.type !== 'all') {
                result = result.filter(p => {
                    const isVideo = p.file_type === 'video';
                    return filter.type === 'video' ? isVideo : !isVideo;
                });
            }
            if (filter.tag) {
                result = result.filter(p => (p.tags || []).includes(filter.tag));
            }
            if (filter.rating) {
                const r = parseInt(filter.rating);
                if (!isNaN(r)) {
                    result = result.filter(p => (p.rating || 0) === r);
                }
            }

            return result;
        });

        const visiblePhotos = Vue.computed(() => {
            const normal = filteredPhotos.value.filter(p => (p.rating || 0) >= 0);
            const collapsed = filteredPhotos.value.filter(p =>
                (p.rating || 0) < 0 && ui.collapsedYears.includes(p.year)
            );
            // 按年份倒序 + 每年内按 sortBy/sortOrder 排序，与 displayedGroupedPhotos 顺序一致
            function sortByYearAndField(arr) {
                const byYear = {};
                arr.forEach(p => {
                    if (!byYear[p.year]) byYear[p.year] = [];
                    byYear[p.year].push(p);
                });
                const years = Object.keys(byYear).sort((a, b) => b - a);
                const result = [];
                for (const year of years) {
                    const field = sortBy[year] || 'create_time';
                    const order = sortOrder[year] === 'asc' ? 1 : -1;
                    byYear[year].sort((a, b) => {
                        if (a._lastModified && !b._lastModified) return 1;
                        if (!a._lastModified && b._lastModified) return -1;
                        if (a._lastModified && b._lastModified) {
                            return a._lastModified - b._lastModified;
                        }
                        return (a[field] > b[field] ? 1 : -1) * order;
                    });
                    result.push(...byYear[year]);
                }
                return result;
            }
            return [...sortByYearAndField(normal), ...sortByYearAndField(collapsed)];
        });

        // 统一年份下拉数据源：分年份模式用API返回的列表，全量模式用本地计算
        const yearDropdownData = Vue.computed(() => {
            if (useYearMode.value) {
                return albumYearList.value.map(y => ({
                    year: String(y.year),
                    count: y.count
                }));
            }
            return Object.keys(yearCounts.value).sort((a, b) => b - a).map(year => ({
                year: String(year),
                count: yearCounts.value[year]
            }));
        });

        // 年份下拉"全部"选项的计数
        const yearAllCount = Vue.computed(() => {
            if (useYearMode.value) {
                return albumYearList.value.reduce((sum, y) => sum + y.count, 0);
            }
            return Object.values(yearCounts.value).reduce((a, b) => a + b, 0);
        });

        const displayedYears = Vue.computed(() => {
            return Object.keys(displayedGroupedPhotos.value).filter(year => {
                const display = displayedGroupedPhotos.value[year];
                if (!display) return false;
                if (display.normal.length > 0) return true;
                if (groupedPhotos.value[year] && groupedPhotos.value[year].normal.length === 0 && groupedPhotos.value[year].collapsed.length > 0) return true;
                return false;
            }).sort((a, b) => b - a);
        });

        const canEditTime = Vue.computed(() => {
            if (!ui.detailPhoto) return false;
            const editCount = ui.detailPhoto.edit_count || 0;
            return editCount < 2;
        });

        // ============ 计算函数 ============
        function computeBasePhotos() {
            let result = albumPhotos.value.slice();
            if (filter.year) {
                result = result.filter(p => String(p.year) === String(filter.year));
            }
            basePhotos.value = result;
        }

        function countPhotosInYearGroups(byYear) {
            let count = 0;
            for (const year in byYear) {
                count += byYear[year].normal.length + byYear[year].collapsed.length;
            }
            return count;
        }

        function computeGroupedPhotos() {
            let result = basePhotos.value.slice();

            if (filter.type && filter.type !== 'all') {
                result = result.filter(p => {
                    const isVideo = p.file_type === 'video';
                    return filter.type === 'video' ? isVideo : !isVideo;
                });
            }
            if (filter.tag) {
                result = result.filter(p => (p.tags || []).includes(filter.tag));
            }
            if (filter.rating) {
                const r = parseInt(filter.rating);
                if (!isNaN(r)) {
                    result = result.filter(p => (p.rating || 0) === r);
                }
            }

            const byYear = {};
            result.forEach(p => {
                if (!byYear[p.year]) byYear[p.year] = { normal: [], collapsed: [] };
                if ((p.rating || 0) < 0) {
                    byYear[p.year].collapsed.push(p);
                } else {
                    byYear[p.year].normal.push(p);
                }
            });

            for (const year of Object.keys(byYear)) {
                const field = sortBy[year] || 'create_time';
                const order = sortOrder[year] === 'asc' ? 1 : -1;

                byYear[year].normal.sort((a, b) => {
                    if (a._lastModified && !b._lastModified) return 1;
                    if (!a._lastModified && b._lastModified) return -1;
                    if (a._lastModified && b._lastModified) {
                        return a._lastModified - b._lastModified;
                    }
                    return (a[field] > b[field] ? 1 : -1) * order;
                });

                byYear[year].collapsed.sort((a, b) => {
                    if (a._lastModified && !b._lastModified) return -1;
                    if (!a._lastModified && b._lastModified) return 1;
                    if (a._lastModified && b._lastModified) {
                        return b._lastModified - a._lastModified;
                    }
                    return (a[field] > b[field] ? 1 : -1) * order;
                });
            }

            groupedPhotos.value = byYear;
            visibleYears.value = Object.keys(byYear).sort((a, b) => b - a);

            // 分批渲染：只取前 renderState.count 条 normal 照片，减少 DOM 节点
            // collapsed 照片用户展开时直接渲染，不受 maxRender 限制
            const displayResult = {};
            let renderedCount = 0;
            const maxRender = renderState ? renderState.count : Infinity;
            let normalTotal = 0;

            for (const year of visibleYears.value) {
                const group = byYear[year];
                normalTotal += group ? group.normal.length : 0;

                if (!group) {
                    displayResult[year] = { normal: [], collapsed: [] };
                    continue;
                }

                const remaining = maxRender - renderedCount;
                if (remaining <= 0) {
                    displayResult[year] = { normal: [], collapsed: [] };
                    continue;
                }

                const normalLen = group.normal.length;
                if (normalLen <= remaining) {
                    displayResult[year] = {
                        normal: group.normal,
                        collapsed: []
                    };
                    renderedCount += normalLen;
                } else {
                    displayResult[year] = {
                        normal: group.normal.slice(0, remaining),
                        collapsed: []
                    };
                    renderedCount = maxRender;
                }
            }

            // collapsed 照片：始终填充，由 CSS .hidden 控制可见性
            for (const year of visibleYears.value) {
                const group = byYear[year];
                if (!group || group.collapsed.length === 0) continue;

                displayResult[year].collapsed = group.collapsed;
            }

            displayedGroupedPhotos.value = displayResult;

            if (renderState) {
                renderState.hasMore = renderedCount < normalTotal;
                renderState.total = normalTotal;
                renderState.rendered = renderedCount;
            }
        }

        function computeYearCounts() {
            const counts = {};
            albumPhotos.value.forEach(p => {
                counts[p.year] = (counts[p.year] || 0) + 1;
            });
            yearCounts.value = counts;
        }

        function computeAvailableTags() {
            const albumTags = new Set();
            albumPhotos.value.forEach(p => {
                (p.tags || []).forEach(tag => albumTags.add(tag));
            });
            const result = {};
            albumTags.forEach(tag => {
                const tagInfo = summary.value.tags?.[tag];
                if (tagInfo) {
                    result[tag] = tagInfo;
                } else {
                    result[tag] = { color: U.getRandomTagColor(tag) };
                }
            });
            availableTags.value = result;
        }

        function refreshComputed() {
            computeGroupedPhotos();
            computeYearCounts();
            computeAvailableTags();
        }

        // ============ 数据加载 ============
        async function loadSummary(retries = C.RETRY_SUMMARY) {
            try {
                summary.value = await Api.fetchSummary();
                if (summary.value.status === 'loading') {
                    if (retries > 0) {
                        await new Promise(resolve => setTimeout(resolve, C.RETRY_INTERVAL));
                        return await loadSummary(retries - 1);
                    } else {
                        console.warn('加载summary超时');
                    }
                }
                albumOrder.value = summary.value.album_order || Object.keys(summary.value.members || {});
                if (!filter.album && summary.value.members && Object.keys(summary.value.members).length > 0) {
                    filter.album = albumOrder.value[0];
                }
            } catch (e) {
                console.error(e);
            }
        }

        function applyPhotosData(photosData, yearData) {
            if (yearData) {
                if (yearData.use_year_mode) {
                    useYearMode.value = true;
                    albumYearList.value = yearData.years || [];
                    if (yearData.selected_year !== undefined && yearData.selected_year !== null && filter.year !== yearData.selected_year) {
                        filter.year = yearData.selected_year;
                    }
                } else {
                    useYearMode.value = false;
                    albumYearList.value = [];
                    if (filter.year) {
                        filter.year = '';
                    }
                }
            }

            let photoList = (photosData && photosData.photos) || [];
            photoList = photoList.map(p => ({
                ...p,
                filename: p.filename || '',
                title: p.title || '',
                tags: Array.isArray(p.tags) ? p.tags : [],
                comment_count: typeof p.comment_count === 'number' ? p.comment_count : 0,
                rating: typeof p.rating === 'number' ? p.rating : 0,
                year: p.year || '未知',
                album_id: p.album_id || '',
                album_name: p.album_name || '',
                file_type: p.file_type || 'image'
            }));

            albumPhotos.value = photoList;
            computeBasePhotos();
            refreshComputed();
            ui.collapsedYears = Object.keys(groupedPhotos.value);
            setTimeout(() => {
                Object.keys(groupedPhotos.value).forEach(year => {
                    if (groupedPhotos.value[year] && groupedPhotos.value[year].normal.length === 0 && groupedPhotos.value[year].collapsed.length > 0) {
                        const idx = ui.collapsedYears.indexOf(year);
                        if (idx !== -1) {
                            ui.collapsedYears.splice(idx, 1);
                        }
                    }
                });
            }, 0);
            contentKey.value++;
        }

        // ============ 分批渲染 ============
        function resetRenderCount() {
            if (renderState) {
                renderState.count = C.INITIAL_RENDER_COUNT;
            }
        }

        function increaseRenderCount() {
            if (renderState && renderState.hasMore) {
                renderState.count += C.RENDER_BATCH_SIZE;
                refreshComputed();
            }
        }

        // ============ 列表同步辅助函数 ============
        function updatePhotoInLists(pathKey, patch) {
            basePhotos.value = basePhotos.value.map(p =>
                p.path_key === pathKey ? { ...p, ...patch } : p
            );
            albumPhotos.value = albumPhotos.value.map(p =>
                p.path_key === pathKey ? { ...p, ...patch } : p
            );
            refreshComputed();
        }

        function updatePhotoInListsBatch(updates) {
            const patchMap = {};
            updates.forEach(u => { patchMap[u.path_key] = u.patch; });
            basePhotos.value = basePhotos.value.map(p =>
                patchMap[p.path_key] ? { ...p, ...patchMap[p.path_key] } : p
            );
            albumPhotos.value = albumPhotos.value.map(p =>
                patchMap[p.path_key] ? { ...p, ...patchMap[p.path_key] } : p
            );
            refreshComputed();
        }

        function removePhotoFromLists(pathKey) {
            basePhotos.value = basePhotos.value.filter(p => p.path_key !== pathKey);
            albumPhotos.value = albumPhotos.value.filter(p => p.path_key !== pathKey);
            refreshComputed();
        }

        function removePhotosFromLists(pathKeys) {
            const keySet = new Set(pathKeys);
            basePhotos.value = basePhotos.value.filter(p => !keySet.has(p.path_key));
            albumPhotos.value = albumPhotos.value.filter(p => !keySet.has(p.path_key));
            refreshComputed();
        }

        return {
            // 计算属性
            filteredPhotos,
            visiblePhotos,
            yearDropdownData,
            yearAllCount,
            displayedYears,
            canEditTime,
            // 计算函数
            computeBasePhotos,
            computeGroupedPhotos,
            computeYearCounts,
            computeAvailableTags,
            refreshComputed,
            // 数据加载
            loadSummary,
            applyPhotosData,
            // 分批渲染
            resetRenderCount,
            increaseRenderCount,
            // 列表同步
            updatePhotoInLists,
            updatePhotoInListsBatch,
            removePhotoFromLists,
            removePhotosFromLists
        };
    }

    window.usePhotos = usePhotos;
})();
