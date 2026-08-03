// 內部使用者的登入狀態（FR-005）。
//
// HR、主管與出題三個頁面共用同一組權杖，因此「沒登入該去哪」「權杖過期怎麼辦」
// 只在這裡定義一次。應徵者不使用本模組——他們沒有帳號，以連結中的 token 識別身分。

import { getAuthToken, clearAuthToken } from './api.js';

const LOGIN_PAGE = '/login.html';
const PROFILE_KEY = 'recruitment.profile';

/** 登入後由 login.js 記下，供各頁顯示「你是誰」。非授權依據。 */
export function setProfile(profile) {
  window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

export function getProfile() {
  try {
    return JSON.parse(window.localStorage.getItem(PROFILE_KEY) || 'null');
  } catch {
    return null;
  }
}

/** 導向登入頁，並記住原本要去的位置，登入後好送回來。 */
export function goToLogin() {
  const next = window.location.pathname + window.location.search;
  window.location.replace(`${LOGIN_PAGE}?next=${encodeURIComponent(next)}`);
}

/**
 * 尚未登入就直接導向登入頁。
 *
 * @returns {boolean} 已登入時為 true；否則已觸發導向，呼叫端應立即停止。
 */
export function requireSession() {
  if (getAuthToken()) return true;
  goToLogin();
  return false;
}

/**
 * 權杖無效或過期時清掉並重新登入。
 *
 * 只認 401／403——其餘錯誤（網址不對、後端沒開）重新登入也解決不了，
 * 把使用者踢去登入頁只會讓真正的原因更難被發現。
 */
export function handleAuthFailure(status) {
  if (status !== 401 && status !== 403) return false;
  clearAuthToken();
  goToLogin();
  return true;
}
