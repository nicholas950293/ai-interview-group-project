// AI 助教對話介面（FR-049～FR-052）。
//
// 助教不可用時，作答、試跑與提交都不受影響（FR-052）——因此這個模組的
// 任何失敗都只寫進自己的錯誤區塊，絕不拋到呼叫端。

import { candidate, ApiError } from './api.js';

const log = document.getElementById('chat-log');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');

export function mountChat({ token, onError }) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage('candidate', message);
    input.value = '';
    const pending = appendMessage('assistant', '思考中…');

    try {
      const result = await candidate.chat(token, message);
      pending.replaceWith(renderAssistant(result.reply, result.guardrail_triggered));
    } catch (error) {
      pending.remove();
      const message503 = 'AI 助教目前不可用。你仍然可以作答、試跑與提交。';
      onError?.(
        error instanceof ApiError && error.status === 503
          ? message503
          : '助教回覆失敗，請稍後再試。你仍然可以作答、試跑與提交。',
      );
    }
  });
}

function appendMessage(role, content) {
  const bubble = document.createElement('div');
  bubble.className =
    role === 'candidate'
      ? 'ml-8 rounded bg-slate-900 px-3 py-2 text-white whitespace-pre-wrap'
      : 'mr-8 rounded bg-slate-100 px-3 py-2 whitespace-pre-wrap';
  bubble.textContent = content;
  log.append(bubble);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function renderAssistant(reply, guardrailTriggered) {
  const wrapper = document.createElement('div');
  wrapper.className = 'mr-8 rounded bg-slate-100 px-3 py-2 space-y-1';

  const body = document.createElement('div');
  body.className = 'whitespace-pre-wrap';
  body.textContent = reply;
  wrapper.append(body);

  if (guardrailTriggered) {
    // 讓應徵者知道助教刻意沒有給完整解答，而不是回答得不好（FR-050）
    const hint = document.createElement('div');
    hint.className = 'text-xs text-slate-500';
    hint.textContent = '助教僅提供觀念引導，不提供可直接提交的完整解答。';
    wrapper.append(hint);
  }

  log.append(wrapper);
  log.scrollTop = log.scrollHeight;
  return wrapper;
}
