/**
 * 通知系统 composable - 提供 showToast 与全局错误监听
 * 遵循单一职责原则：仅负责通知显示
 * 依赖：Vue, constants.js（window.AppConstants）
 */
(function () {
    'use strict';

    const { ref } = Vue;
    const C = window.AppConstants;

    /**
     * @returns {{notifications, showToast, initGlobalErrorHandling}}
     */
    function useNotifications() {
        const notifications = ref([]);
        let notifId = 0;

        /** 显示一条通知，NOTIFICATION_DURATION 后自动消失 */
        function showToast(msg, type) {
            const id = ++notifId;
            notifications.value.push({ id, msg, type: type || 'info' });
            setTimeout(() => {
                notifications.value = notifications.value.filter(n => n.id !== id);
            }, C.NOTIFICATION_DURATION);
        }

        /** 注册全局未捕获异常与网络状态监听 */
        function initGlobalErrorHandling() {
            window.addEventListener('unhandledrejection', (event) => {
                console.error('Unhandled Rejection:', event.reason);
                showToast('系统异常，请刷新重试', 'error');
            });

            window.addEventListener('error', (event) => {
                console.error('Global Error:', event.error);
                showToast('系统异常，请刷新重试', 'error');
            });

            window.addEventListener('online', () => {
                showToast('网络已恢复', 'success');
            });

            window.addEventListener('offline', () => {
                showToast('网络已断开', 'error');
            });
        }

        return { notifications, showToast, initGlobalErrorHandling };
    }

    window.useNotifications = useNotifications;
})();
