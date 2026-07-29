/**
 * 订阅介绍页交互
 * 依赖：subscribe.css
 */
(function () {
    'use strict';

    // 返回按钮：优先 history.back()，无历史则跳转首页
    var backLink = document.getElementById('backLink');
    if (backLink) {
        backLink.addEventListener('click', function (e) {
            e.preventDefault();
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = '/';
            }
        });
    }

    // 套餐卡片 hover 上浮效果已通过 CSS transition 实现，无需额外 JS
})();
