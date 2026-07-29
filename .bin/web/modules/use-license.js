/**
 * 授权码 composable - 授权状态查询、激活、清除及组合弹窗
 * 遵循单一职责原则：仅负责授权相关逻辑
 * 依赖：无外部依赖，直接使用 fetch
 */
(function () {
    'use strict';

    /**
     * @returns {{getLicenseStatus, activateLicense, clearLicense, promptLicenseAndPassword}}
     */
    function useLicense() {
        /**
         * 获取授权状态（每次调用都请求后端，不缓存）
         * @returns {Promise<object>} 授权状态对象
         */
        async function getLicenseStatus() {
            try {
                const res = await fetch('/api/license/status');
                return await res.json();
            } catch (e) {
                return { has_license: false, in_free_trial: false, first_upload_time: null, error: e.message };
            }
        }

        /**
         * 激活授权码
         * @param {string} code 授权码
         * @param {string} password 密码（用于 X-Auth 头）
         * @returns {Promise<object>} 激活结果
         */
        async function activateLicense(code, password) {
            const res = await fetch('/api/license/activate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Auth': password },
                body: JSON.stringify({ code })
            });
            return await res.json();
        }

        /**
         * 清除授权码
         * @param {string} password 密码（用于 X-Auth 头）
         * @returns {Promise<object>} 清除结果
         */
        async function clearLicense(password) {
            const res = await fetch('/api/license/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Auth': password }
            });
            return await res.json();
        }

        /**
         * 弹出授权码 + 密码组合输入框
         * 支持单独验证：可只输入授权码或只输入密码提交
         * 授权码错误→红字；授权码正确→绿字提醒；未输入授权码→红字"请输入授权码"
         * 只有授权码和密码都正确，才关闭弹窗
         * 返回 { code, password } 或 null（用户取消）
         * @returns {Promise<{code:string,password:string}|null>}
         */
        async function promptLicenseAndPassword() {
            const Api = window.AppApi;
            return new Promise((resolve) => {
                const modal = document.createElement('div');
                modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';

                const content = document.createElement('div');
                content.style.cssText = 'background:white;padding:24px;border-radius:12px;width:320px;text-align:center;';
                content.innerHTML = `
                    <h3 style="margin-bottom:16px;font-size:16px;">请输入授权码和密码</h3>
                    <input type="text" id="license-input" style="width:100%;padding:10px;border:1px solid #ddd;border-radius:8px;margin-bottom:8px;font-size:14px;box-sizing:border-box;" placeholder="输入授权码">
                    <div style="text-align:right;margin-bottom:12px;">
                        <a href="/subscribe.html" target="_blank" style="color:#667eea;font-size:12px;text-decoration:none;">订阅授权码</a>
                    </div>
                    <input type="password" id="license-pwd-input" style="width:100%;padding:10px;border:1px solid #ddd;border-radius:8px;margin-bottom:8px;font-size:14px;box-sizing:border-box;" placeholder="输入密码">
                    <div id="license-msg" style="min-height:20px;font-size:13px;margin-bottom:12px;line-height:20px;"></div>
                    <div style="display:flex;gap:12px;justify-content:flex-end;">
                        <button id="license-cancel" style="padding:8px 16px;border:1px solid #ddd;border-radius:8px;background:white;cursor:pointer;">取消</button>
                        <button id="license-submit" style="padding:8px 16px;border:none;border-radius:8px;background:#667eea;color:white;cursor:pointer;">确定</button>
                    </div>
                `;

                modal.appendChild(content);
                document.body.appendChild(modal);

                const codeInput = content.querySelector('#license-input');
                const pwdInput = content.querySelector('#license-pwd-input');
                const msgEl = content.querySelector('#license-msg');
                const submitBtn = content.querySelector('#license-submit');
                const cancelBtn = content.querySelector('#license-cancel');

                let busy = false;

                const doSubmit = async () => {
                    if (busy) return;
                    const code = codeInput.value.trim();
                    const pwd = pwdInput.value;

                    // 未输入授权码
                    if (!code) {
                        msgEl.textContent = '请输入授权码';
                        msgEl.style.color = '#ff5252';
                        return;
                    }

                    busy = true;

                    // 验证授权码
                    const activateResult = await activateLicense(code, pwd || '');
                    if (!activateResult.success) {
                        msgEl.textContent = activateResult.message || '授权码错误';
                        msgEl.style.color = '#ff5252';
                        busy = false;
                        return;
                    }

                    // 授权码正确，但未输入密码
                    if (!pwd) {
                        msgEl.textContent = '授权码正确';
                        msgEl.style.color = '#4caf50';
                        busy = false;
                        return;
                    }

                    // 验证密码
                    const pwdOk = await Api.verifyPassword(pwd);
                    busy = false;
                    if (!pwdOk) {
                        msgEl.textContent = '密码错误';
                        msgEl.style.color = '#ff5252';
                        return;
                    }

                    // 都正确
                    modal.remove();
                    resolve({ code, password: pwd });
                };

                submitBtn.onclick = doSubmit;
                pwdInput.onkeydown = (e) => {
                    if (e.key === 'Enter') doSubmit();
                };
                codeInput.onkeydown = (e) => {
                    if (e.key === 'Enter') pwdInput.focus();
                };
                cancelBtn.onclick = () => {
                    modal.remove();
                    resolve(null);
                };

                codeInput.focus();
            });
        }

        return { getLicenseStatus, activateLicense, clearLicense, promptLicenseAndPassword };
    }

    window.useLicense = useLicense;
})();
