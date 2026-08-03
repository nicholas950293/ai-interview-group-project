// 狀態提示區（FR-110、NFR-006）。
//
// 只做一件事：把 gate 的判定結果寫進提示區。它不決定顯示什麼狀態——那是
// core/gate.js 的責任。

import { NOTICE_MESSAGES } from '../core/messages.js';

const BASE_CLASS = 'notice';

// 語氣分級：逾期是「你錯過了」，找不到／載入失敗是「出事了」，其餘為中性告知
const LEVEL_CLASS = {
  EXPIRED: 'notice--warn',
  NOT_FOUND: 'notice--error',
  LINK_INCOMPLETE: 'notice--error',
  LOAD_FAILED: 'notice--error',
  PREPARING: 'notice--info',
  SUBMITTED: 'notice--info',
};

export function showNotice(element, gate) {
  if (!element) return;
  const { state, message } = gate || {};
  element.className = `${BASE_CLASS} ${LEVEL_CLASS[state] || 'notice--info'}`;
  element.textContent = message || NOTICE_MESSAGES[state] || '';
  element.hidden = false;
}

export function hideNotice(element) {
  if (!element) return;
  element.hidden = true;
  element.classList.add('hidden');
}
