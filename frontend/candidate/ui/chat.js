// AI 助教對話（FR-128～FR-131）。
//
// 兩項不變條件：
//   1. 這個模組的任何失敗都只寫進自己的錯誤區塊，絕不拋到呼叫端——助教不可用時
//      作答、試跑與提交必須完全不受影響（FR-129）。
//   2. 容器由呼叫端注入，模組載入時不抓取任何全域 DOM，因此可獨立掛載（FR-131）。
//
// 送出的實際請求由呼叫端提供的 `onSend` 執行；本模組不接觸 API。

import { CHAT_MESSAGES } from '../core/messages.js';

const ROLE_LABEL = { candidate: '你', assistant: 'AI 助教' };

function messageRow(role, modifier = '') {
  const row = document.createElement('div');
  row.className = `msg msg--${role}${modifier}`;

  const label = document.createElement('div');
  label.className = 'msg__label';
  label.textContent = ROLE_LABEL[role] || role;

  const bubble = document.createElement('div');
  bubble.className = 'msg__bubble';

  row.append(label, bubble);
  return { row, bubble };
}

export function createChatPanel({ log, form, input, error, quickAsks, onSend }) {
  let pending = false;

  function scrollToLatest() {
    log.scrollTop = log.scrollHeight;
  }

  function appendMessage(role, content) {
    const { row, bubble } = messageRow(role);
    bubble.textContent = content;
    log.append(row);
    scrollToLatest();
    return row;
  }

  /** 等待中的暫時訊息：小圓點 + 「思考中…」，與正式回覆的樣式明確區分。 */
  function appendPending() {
    const { row, bubble } = messageRow('assistant', ' msg--pending');
    const dot = document.createElement('span');
    dot.className = 'dot';
    bubble.append(dot, document.createTextNode(CHAT_MESSAGES.PENDING));
    log.append(row);
    scrollToLatest();
    return row;
  }

  function appendAssistant(reply, guardrailTriggered) {
    const { row, bubble } = messageRow('assistant');
    bubble.textContent = reply;

    if (guardrailTriggered) {
      // 讓應徵者知道助教是刻意不給完整解答，而不是回答得不好（FR-050）
      const hint = document.createElement('div');
      hint.className = 'msg__guardrail';
      hint.textContent = CHAT_MESSAGES.GUARDRAIL;
      bubble.append(hint);
    }

    log.append(row);
    scrollToLatest();
    return row;
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
    for (const message of history) {
      if (message.role === 'assistant') appendAssistant(message.content, message.guardrailTriggered);
      else appendMessage(message.role, message.content);
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return; // 進行中不重複送出（FR-130）

    const message = input.value.trim();
    if (!message) return;

    pending = true;
    clearError();
    appendMessage('candidate', message);
    input.value = '';
    const placeholder = appendPending();

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

  // 常見問題捷徑：填入輸入框後走與手動送出完全相同的路徑，不另開請求管道
  quickAsks?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-ask]');
    if (!button || pending) return;
    input.value = button.dataset.ask;
    form.requestSubmit();
  });

  // Enter 送出、Shift+Enter 換行——與輸入框改為 textarea 後的預期一致
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  return { restore };
}
