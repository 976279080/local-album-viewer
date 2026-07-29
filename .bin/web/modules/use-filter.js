/**
 * 筛选 composable - 筛选状态管理、下拉菜单控制
 * 遵循单一职责原则：仅负责筛选与下拉相关逻辑
 * 依赖：外部传入的 filter/ui ref 对象、loadPhotos 回调、AppConstants
 */
(function () {
    'use strict';

    function useFilter(
        filter, ui, openDropdown, openSortDropdown,
        sortBy, sortOrder,
        refreshComputedCallback,
        groupedPhotos
    ) {
        // ============ 筛选与下拉 ============
        function toggleDropdown(name) {
            openDropdown.value = openDropdown.value === name ? null : name;
        }

        function closeAllDropdowns() {
            openDropdown.value = null;
            openSortDropdown.value = null;
        }

        function toggleCollapsed(year) {
            const idx = ui.collapsedYears.indexOf(year);
            if (idx > -1) {
                ui.collapsedYears.splice(idx, 1);
            } else {
                ui.collapsedYears.push(year);
            }
        }

        function isCollapsedVisible(year) {
            return !ui.collapsedYears.includes(year);
        }

        // ============ 排序 ============
        function changeSort(value, year) {
            const parts = value.split('_');
            const order = parts.pop();
            const by = parts.join('_');
            if (year) {
                sortOrder[year] = order;
                sortBy[year] = by;
                refreshComputedCallback();
            }
        }

        return {
            toggleDropdown,
            closeAllDropdowns,
            toggleCollapsed,
            isCollapsedVisible,
            changeSort
        };
    }

    window.useFilter = useFilter;
})();
