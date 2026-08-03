// 狀態提示區（FR-110、NFR-006）。
//
// 只做一件事：把 gate 的判定結果寫進提示區。它不決定顯示什麼狀態——那是
// core/gate.js 的責任。

import { NOTICE_MESSAGES } from '../core/messages.js';

const BASE_CLASS = 'max-w-3xl mx-auto mt-10 rounded border p-6 text-sm';

// 語氣分級：逾期是「你錯過了」，找不到／載入失敗是「出事了」，其餘為中性告知
const LEVEL_CLASS = {
  EXPIRED: 'border-amber-300 bg-amber-50 text-amber-800',
  NOT_FOUND: 'border-red-300 bg-red-50 text-red-700',
  LINK_INCOMPLETE: 'border-red-300 bg-red-50 text-red-700',
  LOAD_FAILED: 'border-red-300 bg-red-50 text-red-700',
  PREPARING: 'border-slate-300 bg-white text-slate-700',
  SUBMITTED: 'border-slate-300 bg-white text-slate-700',
};

const NEUTRAL = 'border-slate-300 bg-white text-slate-700';

export function showNotice(element, gate) {
  if (!element) return;
  const { state, message } = gate || {};
  element.className = `${BASE_CLASS} ${LEVEL_CLASS[state] || NEUTRAL}`;
  element.textContent = message || NOTICE_MESSAGES[state] || '';
  element.hidden = false;
  element.classList.remove('hidden');
}

export function hideNotice(element) {
  if (!element) return;
  element.hidden = true;
  element.classList.add('hidden');
}
