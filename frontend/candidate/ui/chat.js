// AI 助教對話（FR-128～FR-131）。
//
// 兩項不變條件：
//   1. 這個模組的任何失敗都只寫進自己的錯誤區塊，絕不拋到呼叫端——助教不可用時
//      作答、試跑與提交必須完全不受影響（FR-129）。
//   2. 容器由呼叫端注入，模組載入時不抓取任何全域 DOM，因此可獨立掛載（FR-131）。
//
// 送出的實際請求由呼叫端提供的 `onSend` 執行；本模組不接觸 API。

import { CHAT_MESSAGES } from '../core/messages.js';

const BUBBLE_CLASS = {
  candidate: 'ml-8 rounded bg-slate-900 px-3 py-2 text-white whitespace-pre-wrap',
  assistant: 'mr-8 rounded bg-slate-100 px-3 py-2 whitespace-pre-wrap',
};

export function createChatPanel({ log, form, input, error, onSend }) {
  let pending = false;

  function scrollToLatest() {
    log.scrollTop = log.scrollHeight;
  }

  function appendBubble(role, content) {
    const bubble = document.createElement('div');
    bubble.className = BUBBLE_CLASS[role] || BUBBLE_CLASS.assistant;
    bubble.textContent = content;
    log.append(bubble);
    scrollToLatest();
    return bubble;
  }

  function appendAssistant(reply, guardrailTriggered) {
    const wrapper = document.createElement('div');
    wrapper.className = 'mr-8 rounded bg-slate-100 px-3 py-2 space-y-1';

    const body = document.createElement('div');
    body.className = 'whitespace-pre-wrap';
    body.textContent = reply;
    wrapper.append(body);

    if (guardrailTriggered) {
      // 讓應徵者知道助教是刻意不給完整解答，而不是回答得不好（FR-050）
      const hint = document.createElement('div');
      hint.className = 'text-xs text-slate-500';
      hint.textContent = CHAT_MESSAGES.GUARDRAIL;
      wrapper.append(hint);
    }

    log.append(wrapper);
    scrollToLatest();
    return wrapper;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    error.classList.remove('hidden');
  }

  function clearError() {
    error.hidden = true;
    error.classList.add('hidden');
  }

  /** 以 session 回傳的對話歷程還原內容（FR-128）。 */
  function restore(history) {
    log.replaceChildren();
    for (const message of history) {
      if (message.role === 'assistant') appendAssistant(message.content, message.guardrailTriggered);
      else appendBubble(message.role, message.content);
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return; // 進行中不重複送出（FR-130）

    const message = input.value.trim();
    if (!message) return;

    pending = true;
    clearError();
    appendBubble('candidate', message);
    input.value = '';
    const placeholder = appendBubble('assistant', CHAT_MESSAGES.PENDING);

    try {
      const result = await onSend(message);
      placeholder.remove();
      appendAssistant(result.reply, result.guardrail_triggered);
    } catch (failure) {
      placeholder.remove();
      const unavailable = failure && failure.status === 503;
      showError(unavailable ? CHAT_MESSAGES.UNAVAILABLE : CHAT_MESSAGES.FAILED);
    } finally {
      pending = false;
    }
  });

  return { restore };
}
