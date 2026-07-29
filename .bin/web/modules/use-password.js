/**
 * 密码输入 composable - 弹窗式密码输入，缓存到 sessionStorage
 * 遵循单一职责原则：仅负责密码获取与缓存
 * 依赖：constants.js（window.AppConstants）、api.js（window.AppApi）
 */
(function () {
    'use strict';

    const C = window.AppConstants;
    const Api = window.AppApi;

    /**
     * @returns {{getPassword, clearPassword, hasPassword}}
     */
    function usePassword() {
        /**
         * 获取密码：优先从 sessionStorage 读取，无则弹窗输入
         * 弹窗内验证密码，错误时红字提醒且不关闭
         * @returns {Promise<string>} 密码（用户取消返回空字符串）
         */
        async function getPassword() {
            let password = sessionStorage.getItem(C.PASSWORD_STORAGE_KEY);
            if (password) return password;

            password = await new Promise((resolve) => {
                const modal = document.createElement('div');
                modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';

                const content = document.createElement('div');
                content.style.cssText = 'background:white;padding:24px;border-radius:12px;width:320px;text-align:center;';
                content.innerHTML = `
                    <h3 style="margin-bottom:16px;font-size:16px;">请输入密码</h3>
                    <input type="password" id="pwd-input" style="width:100%;padding:10px;border:1px solid #ddd;border-radius:8px;margin-bottom:8px;font-size:14px;box-sizing:border-box;" placeholder="输入密码">
                    <div id="pwd-error" style="min-height:20px;font-size:13px;margin-bottom:12px;color:#ff5252;line-height:20px;"></div>
                    <div style="display:flex;gap:12px;justify-content:flex-end;">
                        <button id="pwd-cancel" style="padding:8px 16px;border:1px solid #ddd;border-radius:8px;background:white;cursor:pointer;">取消</button>
                        <button id="pwd-submit" style="padding:8px 16px;border:none;border-radius:8px;background:#667eea;color:white;cursor:pointer;">确定</button>
                    </div>
                `;

                modal.appendChild(content);
                document.body.appendChild(modal);

                const input = content.querySelector('#pwd-input');
                const errorEl = content.querySelector('#pwd-error');
                const submitBtn = content.querySelector('#pwd-submit');
                const cancelBtn = content.querySelector('#pwd-cancel');

                let busy = false;
                const doSubmit = async () => {
                    if (busy) return;
                    const pwd = input.value;
                    if (!pwd) {
                        errorEl.textContent = '请输入密码';
                        return;
                    }
                    busy = true;
                    const ok = await Api.verifyPassword(pwd);
                    busy = false;
                    if (!ok) {
                        errorEl.textContent = '密码错误';
                        input.value = '';
                        input.focus();
                        return;
                    }
                    modal.remove();
                    sessionStorage.setItem(C.PASSWORD_STORAGE_KEY, pwd);
                    resolve(pwd);
                };

                submitBtn.onclick = doSubmit;
                input.onkeydown = (e) => {
                    if (e.key === 'Enter') doSubmit();
                };
                cancelBtn.onclick = () => {
                    modal.remove();
                    resolve('');
                };

                input.focus();
            });

            return password;
        }

        /** 清除缓存的密码（密码错误时调用） */
        function clearPassword() {
            sessionStorage.removeItem(C.PASSWORD_STORAGE_KEY);
        }

        /** 检查是否已有缓存的密码 */
        function hasPassword() {
            return !!sessionStorage.getItem(C.PASSWORD_STORAGE_KEY);
        }

        return { getPassword, clearPassword, hasPassword };
    }

    window.usePassword = usePassword;
})();
