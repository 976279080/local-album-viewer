/**
 * 确认对话框 composable - 提供 Promise 风格的确认弹窗
 * 遵循单一职责原则：仅负责确认对话框状态管理
 * 依赖：Vue
 */
(function () {
    'use strict';

    const { reactive } = Vue;

    /**
     * @returns {{confirmState, showConfirm, handleConfirm}}
     */
    function useConfirm() {
        const confirmState = reactive({
            show: false,
            title: '',
            message: '',
            confirmText: '确定',
            cancelText: '取消',
            danger: false,
            resolve: null
        });

        /** 显示确认对话框，返回 Promise<boolean> */
        function showConfirm(options) {
            return new Promise((resolve) => {
                confirmState.title = options.title || '确认';
                confirmState.message = options.message || '确定要执行此操作吗？';
                confirmState.confirmText = options.confirmText || '确定';
                confirmState.cancelText = options.cancelText || '取消';
                confirmState.danger = options.danger || false;
                confirmState.resolve = resolve;
                confirmState.show = true;
            });
        }

        /** 处理用户点击结果 */
        function handleConfirm(result) {
            confirmState.show = false;
            if (confirmState.resolve) {
                confirmState.resolve(result);
                confirmState.resolve = null;
            }
        }

        return { confirmState, showConfirm, handleConfirm };
    }

    window.useConfirm = useConfirm;
})();
