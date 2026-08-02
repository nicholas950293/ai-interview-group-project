// 應徵者作答頁（FR-029～FR-035）。
//
// 依部門類型切換介面：工程類提供 CodeMirror 程式碼編輯器與試跑，
// 非工程類提供結構化文字作答（FR-029）。

import { candidate, ApiError, formatDate } from './api.js';
import { mountChat } from './chat.js';

const CODEMIRROR_CDN = 'https://esm.sh/codemirror@6.0.1';
const LANGUAGE_CDN = {
  javascript: 'https://esm.sh/@codemirror/lang-javascript@6.2.2',
  python: 'https://esm.sh/@codemirror/lang-python@6.1.6',
  go: 'https://esm.sh/@codemirror/lang-go@6.0.1',
  java: 'https://esm.sh/@codemirror/lang-java@6.0.1',
  cpp: 'https://esm.sh/@codemirror/lang-cpp@6.0.2',
};

const token = new URLSearchParams(window.location.search).get('token') || '';
const notice = document.getElementById('notice');
const workspace = document.getElementById('workspace');
const output = document.getElementById('run-output');
const runMeta = document.getElementById('run-meta');

let editor = null;          // CodeMirror 實例；載入失敗時為 null
let fallbackArea = null;    // 退回的 textarea
let session = null;
let isEngineering = true;

// ── 啟動 ──────────────────────────────────────────────────────────────

async function boot() {
  if (!token) return showNotice('連結不完整，請確認信件中的網址是否完整複製。', 'error');

  try {
    session = await candidate.getSession(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 410) {
      // 逾期不顯示題目內容（FR-018）
      return showNotice(`${error.message}`, 'warn');
    }
    if (error instanceof ApiError && error.status === 404) {
      return showNotice('找不到此測驗連結，請確認網址或聯繫 HR。', 'error');
    }
    return showNotice('載入失敗，請稍後重新整理頁面。', 'error');
  }

  if (session.status === 'PENDING_ASSIGN') {
    return showNotice('題目準備中，請稍後再開啟此連結。', 'info');
  }
  if (session.submitted_at) {
    return showNotice(
      `你已於 ${formatDate(session.submitted_at)} 完成提交，本連結已轉為唯讀。`,
      'info',
    );
  }

  render();
}

function showNotice(message, level) {
  const styles = {
    info: 'border-slate-300 bg-white text-slate-700',
    warn: 'border-amber-300 bg-amber-50 text-amber-800',
    error: 'border-red-300 bg-red-50 text-red-700',
  };
  notice.className = `max-w-3xl mx-auto mt-10 rounded border p-6 text-sm ${styles[level]}`;
  notice.textContent = message;
  notice.classList.remove('hidden');
}

// ── 畫面 ──────────────────────────────────────────────────────────────

async function render() {
  workspace.classList.remove('hidden');
  isEngineering = session.dept_type === 'ENGINEERING';

  document.getElementById('job-title').textContent = `線上測驗｜${session.job_title}`;
  document.getElementById('expires-at').textContent = `連結到期：${formatDate(session.token_expires_at)}`;
  updateTrialRemaining(session.trial_runs_remaining);

  const question = session.question || {};
  document.getElementById('question-title').textContent = question.title || '';
  document.getElementById('question-description').textContent = question.description || '';
  document.getElementById('question-constraints').textContent = question.constraints || '';
  renderSampleCases(question.sample_cases || []);

  if (isEngineering) {
    await mountEditor(question.language || session.code_language || 'python');
  } else {
    // 非工程類：文字作答，隱藏語言選擇與試跑（FR-029）
    document.getElementById('code-editor').classList.add('hidden');
    document.getElementById('text-answer').classList.remove('hidden');
    document.getElementById('language-select').closest('label').classList.add('hidden');
    document.getElementById('btn-run').classList.add('hidden');
    document.getElementById('run-stdin').closest('label').classList.add('hidden');
  }

  mountChat({ token, onError: (message) => showChatError(message) });
}

function renderSampleCases(cases) {
  const container = document.getElementById('sample-cases');
  container.replaceChildren(
    ...cases.map((testCase) => {
      const block = document.createElement('div');
      block.className = 'rounded border border-slate-200 p-2';
      block.innerHTML = `
        <div class="font-medium">${escapeHtml(testCase.name)}</div>
        <div class="mt-1 grid gap-1 sm:grid-cols-2 font-mono">
          <pre class="whitespace-pre-wrap">輸入：${escapeHtml(testCase.stdin)}</pre>
          <pre class="whitespace-pre-wrap">預期：${escapeHtml(testCase.expected_stdout)}</pre>
        </div>`;
      return block;
    }),
  );
}

async function mountEditor(language) {
  const select = document.getElementById('language-select');
  select.value = language;
  select.addEventListener('change', () => mountEditor(select.value));

  const host = document.getElementById('code-editor');
  host.replaceChildren();

  try {
    const [{ EditorView, basicSetup }, langModule] = await Promise.all([
      import(CODEMIRROR_CDN),
      import(LANGUAGE_CDN[language]),
    ]);
    const support = Object.values(langModule).find((value) => typeof value === 'function');
    const doc = currentCode();
    editor = new EditorView({ doc, extensions: [basicSetup, support()], parent: host });
    fallbackArea = null;
  } catch {
    // CDN 不可用時退回純文字輸入——作答能力不得因為語法標示而中斷
    editor = null;
    fallbackArea = document.createElement('textarea');
    fallbackArea.className = 'w-full p-4 font-mono text-sm min-h-[320px]';
    fallbackArea.value = currentCode();
    host.append(fallbackArea);
  }
}

function currentCode() {
  if (editor) return editor.state.doc.toString();
  if (fallbackArea) return fallbackArea.value;
  return '';
}

function answerText() {
  return isEngineering ? currentCode() : document.getElementById('text-answer').value;
}

function updateTrialRemaining(remaining) {
  document.getElementById('trial-remaining').textContent = `剩餘試跑次數：${remaining}`;
  document.getElementById('btn-run').disabled = remaining <= 0;
}

// ── 試跑與提交 ────────────────────────────────────────────────────────

document.getElementById('btn-run').addEventListener('click', async () => {
  output.textContent = '執行中…（若目前有其他人正在執行，會排隊等候）';
  runMeta.textContent = '';

  try {
    const result = await candidate.run(token, {
      code: currentCode(),
      language: document.getElementById('language-select').value,
      stdin: document.getElementById('run-stdin').value,
    });
    output.textContent = [result.stdout, result.stderr].filter(Boolean).join('\n') || '（無輸出）';
    runMeta.textContent = `${describeTermination(result.termination_reason)}｜耗時 ${result.duration_ms} ms${result.truncated ? '｜輸出已截斷' : ''}`;
    session.trial_runs_remaining = Math.max(session.trial_runs_remaining - 1, 0);
    updateTrialRemaining(session.trial_runs_remaining);
  } catch (error) {
    if (error instanceof ApiError && error.status === 429) {
      session.trial_runs_remaining = 0;
      updateTrialRemaining(0);
      output.textContent = `${error.message}`;
      return;
    }
    if (error instanceof ApiError && error.status === 503) {
      // 沙箱不可用不影響提交（FR-047）
      output.textContent = `${error.message}`;
      return;
    }
    output.textContent = error instanceof ApiError ? error.message : '執行失敗，請稍後再試。';
  }
});

document.getElementById('btn-submit').addEventListener('click', async () => {
  if (!window.confirm('提交後將無法修改作答，確定要提交嗎？')) return;

  try {
    const result = await candidate.submit(
      token,
      answerText(),
      isEngineering ? document.getElementById('language-select').value : null,
    );
    workspace.classList.add('hidden');
    // 提交完成後必須顯示明確的成功確認（FR-035）
    showNotice(`已於 ${formatDate(result.submitted_at)} 成功提交，感謝你的作答。`, 'info');
  } catch (error) {
    window.alert(error instanceof ApiError ? error.message : '提交失敗，請稍後再試。');
  }
});

function describeTermination(reason) {
  return {
    COMPLETED: '執行完成',
    TIMEOUT: '執行逾時',
    MEMORY_LIMIT: '超過記憶體上限',
    PIDS_LIMIT: '超過程序數上限',
    OUTPUT_LIMIT: '超過輸出上限',
    COMPILE_ERROR: '編譯／語法錯誤',
    SANDBOX_UNAVAILABLE: '執行環境不可用',
  }[reason] || reason;
}

function showChatError(message) {
  const box = document.getElementById('chat-error');
  box.classList.remove('hidden');
  box.textContent = message;
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

boot();
