// 內部人員登入頁（FR-005）。
//
// 密碼只在這一頁存在，且只往後端送一次——本前端不保存、不記錄、不放進網址。
// 登入成功後保存的是後端簽出的權杖，與既有 HR／主管頁共用同一個位置。

import { auth, setAuthToken, system, ApiError } from './api.js';
import { setProfile } from './session.js';
import { resolveRedirect } from './login-target.js';

const el = (id) => document.getElementById(id);

const dom = {
  form: el('login-form'),
  email: el('email'),
  password: el('password'),
  error: el('login-error'),
  button: el('btn-login'),
  demoHint: el('demo-hint'),
};

const MESSAGES = {
  INVALID: '帳號或密碼錯誤，請再試一次。',
  UNAVAILABLE: '認證服務目前不可用，請稍後再試。',
  NOT_FOUND:
    '找不到後端 API（404）。這一頁多半被開在只提供靜態檔的伺服器上——'
    + '請改用有跑後端的網址，或把 /api 反向代理到後端。',
  NETWORK: '連不上伺服器。請確認後端仍在執行，以及這一頁的網址與後端是同一個來源。',
  FAILED: '登入失敗，請稍後再試。',
};

const DEMO_HINT =
  'demo 模式：HR 帳號 hr@example.com、主管帳號 manager@example.com，密碼皆為 demo1234。'
  + '（合成帳號，非真實憑證）';

let busy = false;

function showError(message) {
  dom.error.textContent = message;
  dom.error.hidden = false;
  dom.error.classList.remove('hidden');
}

function clearError() {
  dom.error.hidden = true;
  dom.error.classList.add('hidden');
}

function describeFailure(error) {
  if (!(error instanceof ApiError)) return MESSAGES.NETWORK;
  if (error.status === 401 || error.status === 403) return MESSAGES.INVALID;
  if (error.status === 404) return MESSAGES.NOT_FOUND;
  if (error.status === 503) return MESSAGES.UNAVAILABLE;
  return error.message || MESSAGES.FAILED;
}

dom.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;

  clearError();
  busy = true;
  dom.button.disabled = true;

  try {
    const session = await auth.login(dom.email.value.trim(), dom.password.value);
    setAuthToken(session.token);
    setProfile({ role: session.role, name: session.name, deptId: session.dept_id });

    // next 來自網址，必須驗證為站內路徑後才導向（見 login-target.js）
    const next = new URLSearchParams(window.location.search).get('next');
    window.location.replace(resolveRedirect(next, session.role));
  } catch (error) {
    showError(describeFailure(error));
    dom.password.value = '';
    dom.password.focus();
  } finally {
    busy = false;
    dom.button.disabled = false;
  }
});

// demo 模式才提示測試帳號。正式環境的登入頁不該印任何憑證。
system
  .health()
  .then((info) => {
    if (!info?.demo_mode) return;
    dom.demoHint.textContent = DEMO_HINT;
    dom.demoHint.hidden = false;
    dom.demoHint.classList.remove('hidden');
  })
  .catch(() => {
    /* 取不到就不顯示提示；登入本身不受影響 */
  });

// 標記模組已成功載入；HTML 的保險腳本以此判斷頁面是否正常
window.__pageReady = true;
