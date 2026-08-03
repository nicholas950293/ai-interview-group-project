// 應徵者頁面的畫面狀態判定（FR-108～FR-111、FR-121、FR-126）。
//
// 這是整個應徵者介面唯一決定「現在該顯示什麼」的地方。它刻意不碰 DOM——
// 逾期、已提交、題目準備中這三種判定是最容易寫錯也最難用手測的部分，
// 抽成純函式後才有辦法逐條驗證（tests/gate.test.js）。
//
// 另一個刻意的選擇：錯誤訊息一律取自本地字串表，不回放後端原文。後端訊息目前
// 是安全的，但「畫面上的文字全部由前端決定」是個不需要持續查核的更強保證（FR-134）。

import { NOTICE_MESSAGES, submittedMessage } from './messages.js';

export const GateState = Object.freeze({
  READY: 'READY',
  LINK_INCOMPLETE: 'LINK_INCOMPLETE',
  NOT_FOUND: 'NOT_FOUND',
  EXPIRED: 'EXPIRED',
  PREPARING: 'PREPARING',
  SUBMITTED: 'SUBMITTED',
  LOAD_FAILED: 'LOAD_FAILED',
});

/** HTTP 狀態碼 → 畫面狀態。未列出者一律視為載入失敗。 */
const STATUS_GATES = {
  404: GateState.NOT_FOUND,
  409: GateState.SUBMITTED,
  410: GateState.EXPIRED,
};

/** READY 以外皆為終端狀態：工作區隱藏、題目不渲染（FR-110）。 */
export function isTerminal(state) {
  return state !== GateState.READY;
}

function gate(state, message = NOTICE_MESSAGES[state]) {
  return { state, message };
}

/**
 * 檢查連結是否帶有 token。
 *
 * 回傳 null 表示「可以繼續發出請求」；回傳狀態則表示連結本身就不完整，
 * 此時**不得**發出任何 API 請求（FR-111）。
 */
export function gateFromToken(token) {
  const value = typeof token === 'string' ? token.trim() : '';
  return value ? null : gate(GateState.LINK_INCOMPLETE);
}

/**
 * 依已載入的 session 判定畫面狀態。
 *
 * `formatDate` 由呼叫端注入，使本模組不相依於地區設定或 Date 行為。
 */
export function gateFromSession(session, { formatDate = String } = {}) {
  const data = session || {};

  // 題目準備中優先——此時沒有題目可顯示（spec.md 邊界情況）
  if (data.status === 'PENDING_ASSIGN') return gate(GateState.PREPARING);
  if (data.status === 'EXPIRED') return gate(GateState.EXPIRED);
  if (data.submitted_at) {
    return gate(GateState.SUBMITTED, submittedMessage(formatDate(data.submitted_at)));
  }
  return gate(GateState.READY, '');
}

/**
 * 依 API 錯誤判定畫面狀態。
 *
 * 同時服務三個場景：初次載入失敗、試跑失敗（FR-121）、提交失敗（FR-126）。
 */
export function gateFromError(error) {
  const status = error && typeof error.status === 'number' ? error.status : 0;
  return gate(STATUS_GATES[status] || GateState.LOAD_FAILED);
}
