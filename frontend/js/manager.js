// 主管 Hub（FR-020、FR-023～FR-028、FR-060～FR-066）。
//
// AI 生成的草稿在主管按下「確認並指派」之前，只存在於這個頁面的記憶體中——
// 後端的 ai-generate 端點不寫入任何資料表（FR-025）。

import { manager, ApiError, STATUS_LABELS, DECISION_LABELS } from './api.js';
import { requireSession, handleAuthFailure } from './session.js';

const listEl = document.getElementById('assessment-list');
const listEmpty = document.getElementById('list-empty');
const placeholder = document.getElementById('detail-placeholder');
const assignPanel = document.getElementById('assign-panel');
const draftEditor = document.getElementById('draft-editor');
const caseList = document.getElementById('case-list');
const assignError = document.getElementById('assign-error');
const aiError = document.getElementById('ai-error');

let assessments = [];
let questionBank = [];
let selectedId = null;

// ── 清單 ──────────────────────────────────────────────────────────────

async function loadAssessments() {
  try {
    assessments = await manager.listAssessments();
  } catch (error) {
    reportError(error);
    return;
  }

  listEl.replaceChildren(
    ...assessments.map((item) => {
      const li = document.createElement('li');
      li.className = 'px-4 py-3 cursor-pointer hover:bg-slate-50';
      li.innerHTML = `
        <div class="text-sm font-medium">${escapeHtml(item.name)}</div>
        <div class="text-xs text-slate-500">
          ${escapeHtml(item.job_title)}｜${STATUS_LABELS[item.status] || item.status}
          ${item.has_report ? '｜已有 AI 報告' : ''}
        </div>`;
      li.addEventListener('click', () => select(item.id));
      return li;
    }),
  );
  listEmpty.classList.toggle('hidden', assessments.length > 0);
}

async function loadQuestionBank() {
  try {
    questionBank = await manager.listQuestions();
  } catch (error) {
    reportError(error);
    return;
  }
  const select = document.getElementById('bank-select');
  select.replaceChildren(new Option('— 請選擇 —', ''));
  for (const question of questionBank) {
    select.append(new Option(`${question.title}（${question.difficulty}）`, question.id));
  }
}

function select(id) {
  selectedId = id;
  const item = assessments.find((a) => a.id === id);
  placeholder.classList.add('hidden');

  // 只有「待指派題目」才顯示出題介面；其餘狀態顯示審閱畫面
  const canAssign = item.status === 'PENDING_ASSIGN';
  assignPanel.classList.toggle('hidden', !canAssign);
  if (canAssign) {
    draftEditor.classList.add('hidden');
    document.getElementById('bank-select').value = '';
  }
  renderReview(item);
}

// ── 題庫挑選與 AI 生成 ────────────────────────────────────────────────

document.getElementById('bank-select').addEventListener('change', (event) => {
  const question = questionBank.find((q) => q.id === event.target.value);
  if (question) fillDraft(question);
});

document.getElementById('ai-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  aiError.classList.add('hidden');
  const skills = document.getElementById('ai-skills').value
    .split(/[,、]/)
    .map((s) => s.trim())
    .filter(Boolean);

  try {
    const draft = await manager.generateQuestion({
      skills,
      difficulty: document.getElementById('ai-difficulty').value,
      language: document.getElementById('ai-language').value,
    });
    fillDraft(draft);
  } catch (error) {
    // AI 不可用時保留主管輸入內容（FR-027）——刻意不清空任何欄位
    aiError.classList.remove('hidden');
    aiError.textContent =
      error instanceof ApiError ? error.message : 'AI 服務暫時無法使用，請稍後再試。';
  }
});

function fillDraft(question) {
  draftEditor.classList.remove('hidden');
  assignError.classList.add('hidden');
  document.getElementById('draft-title').value = question.title || '';
  document.getElementById('draft-category').value = question.category || '';
  document.getElementById('draft-difficulty').value = question.difficulty || 'MEDIUM';
  document.getElementById('draft-language').value = question.language || 'python';
  document.getElementById('draft-description').value = question.description || '';
  document.getElementById('draft-constraints').value = question.constraints || '';
  caseList.replaceChildren(...(question.test_cases || []).map(caseRow));
}

function caseRow(testCase = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'rounded border border-slate-200 p-2 space-y-1 text-xs';
  wrapper.innerHTML = `
    <div class="flex items-center gap-2">
      <input class="case-name flex-1 rounded border border-slate-300 p-1" placeholder="案例名稱">
      <label class="flex items-center gap-1">
        <input type="checkbox" class="case-hidden"> 隱藏測資
      </label>
      <button type="button" class="case-remove rounded border border-slate-300 px-2">移除</button>
    </div>
    <textarea class="case-stdin w-full rounded border border-slate-300 p-1 font-mono" rows="2" placeholder="標準輸入"></textarea>
    <textarea class="case-stdout w-full rounded border border-slate-300 p-1 font-mono" rows="2" placeholder="預期輸出"></textarea>`;

  wrapper.querySelector('.case-name').value = testCase.name || '';
  wrapper.querySelector('.case-stdin').value = testCase.stdin || '';
  wrapper.querySelector('.case-stdout').value = testCase.expected_stdout || '';
  wrapper.querySelector('.case-hidden').checked = Boolean(testCase.is_hidden);
  wrapper.querySelector('.case-remove').addEventListener('click', () => wrapper.remove());
  return wrapper;
}

document.getElementById('add-case').addEventListener('click', () => caseList.append(caseRow()));

function collectDraft() {
  return {
    source: 'AI_GENERATED',
    title: document.getElementById('draft-title').value.trim(),
    category: document.getElementById('draft-category').value.trim() || null,
    difficulty: document.getElementById('draft-difficulty').value,
    language: document.getElementById('draft-language').value,
    description: document.getElementById('draft-description').value.trim(),
    constraints: document.getElementById('draft-constraints').value.trim() || null,
    test_cases: [...caseList.children].map((row) => ({
      name: row.querySelector('.case-name').value.trim() || '未命名案例',
      stdin: row.querySelector('.case-stdin').value,
      expected_stdout: row.querySelector('.case-stdout').value,
      is_hidden: row.querySelector('.case-hidden').checked,
    })),
  };
}

document.getElementById('btn-assign').addEventListener('click', async () => {
  assignError.classList.add('hidden');
  try {
    await manager.assignQuestion(selectedId, collectDraft());
    await loadAssessments();
    select(selectedId);
  } catch (error) {
    assignError.classList.remove('hidden');
    assignError.textContent =
      error instanceof ApiError ? error.message : '指派失敗，請稍後再試。';
  }
});

// ── 審閱畫面與決策（FR-060～FR-066）─────────────────────────────────────
//
// 這個畫面呈現 AI 報告，但決策欄位一律留白——系統不得自動產生綜合錄取建議，
// 綜合判斷必須由主管做出（FR-057、憲章原則 V）。

const DIMENSION_LABELS = {
  correctness: '正確性',
  maintainability: '可維護性',
  performance: '效能',
  security: '安全性',
};

async function renderReview(item) {
  const panel = document.getElementById('review-panel');
  if (item.status === 'PENDING_ASSIGN') {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  panel.replaceChildren(loadingCard(item));

  let detail;
  try {
    detail = await manager.getAssessment(item.id);
  } catch (error) {
    reportError(error);
    return;
  }

  panel.replaceChildren(
    headerCard(detail),
    answerCard(detail),
    executionsCard(detail),
    chatCard(detail),
    reportCard(detail),
    decisionCard(detail),
  );
}

function card(title, innerHtml) {
  const section = document.createElement('div');
  section.className = 'bg-white rounded border border-slate-200';
  section.innerHTML = `
    <h3 class="px-4 py-2 text-sm font-semibold border-b border-slate-200">${title}</h3>
    <div class="p-4 text-sm">${innerHtml}</div>`;
  return section;
}

function loadingCard(item) {
  return card('審閱', `<p class="text-slate-500">載入 ${escapeHtml(item.name)} 的作答內容…</p>`);
}

function headerCard(detail) {
  return card(
    '應徵者',
    `<div class="font-medium">${escapeHtml(detail.name)}｜${escapeHtml(detail.job_title)}</div>
     <div class="mt-1 text-xs text-slate-500">狀態：${STATUS_LABELS[detail.status] || detail.status}</div>`,
  );
}

function answerCard(detail) {
  return card(
    `作答內容${detail.code_language ? `（${escapeHtml(detail.code_language)}）` : ''}`,
    `<pre class="overflow-x-auto whitespace-pre-wrap font-mono text-xs">${escapeHtml(detail.candidate_answer || '（尚未作答）')}</pre>`,
  );
}

function executionsCard(detail) {
  if (!detail.executions.length) return card('執行紀錄', '<p class="text-slate-500">無執行紀錄。</p>');

  const rows = detail.executions
    .map((execution) => {
      const results = execution.test_results;
      const summary = results
        ? `通過 ${results.passed}/${results.total}`
        : '—';
      return `<tr class="border-t border-slate-100">
        <td class="py-1 pr-3">${execution.trigger === 'EVALUATION' ? '評測' : '試跑'}</td>
        <td class="py-1 pr-3">${escapeHtml(execution.termination_reason)}</td>
        <td class="py-1 pr-3">${execution.duration_ms ?? '—'} ms</td>
        <td class="py-1">${summary}</td>
      </tr>`;
    })
    .join('');

  return card(
    '沙箱執行紀錄與測資通過情形',
    `<table class="w-full text-xs">
       <thead><tr class="text-left text-slate-500">
         <th class="pb-1">來源</th><th>中止原因</th><th>耗時</th><th>測資</th>
       </tr></thead>
       <tbody>${rows}</tbody>
     </table>`,
  );
}

function chatCard(detail) {
  if (!detail.ai_chat_history.length) {
    return card('AI 助教對話歷程', '<p class="text-slate-500">應徵者未使用助教。</p>');
  }
  const items = detail.ai_chat_history
    .map(
      (message) => `<div class="mb-2">
        <span class="text-xs text-slate-500">${message.role === 'candidate' ? '應徵者' : '助教'}</span>
        ${message.guardrail_triggered ? '<span class="ml-1 text-xs text-amber-700">（已攔截索取完整解答）</span>' : ''}
        <div class="whitespace-pre-wrap">${escapeHtml(message.content)}</div>
      </div>`,
    )
    .join('');
  return card('AI 助教對話歷程', items);
}

function reportCard(detail) {
  const report = detail.ai_report;
  if (!report) return card('AI 評測報告', '<p class="text-slate-500">尚未產生評測報告。</p>');

  if (report.status !== 'SUCCESS') {
    return card(
      'AI 評測報告',
      `<p class="text-amber-700">評測未成功（${escapeHtml(report.status)}）：${escapeHtml(report.error_message || '未知原因')}</p>
       <button type="button" id="btn-reevaluate" class="mt-2 rounded border border-slate-300 px-3 py-1 text-xs">重新評測</button>
       <p class="mt-2 text-xs text-slate-500">你仍可在沒有 AI 報告的情況下自行審閱並決策。</p>`,
    );
  }

  const dimensions = Object.entries(report.dimensions || {})
    .map(
      ([name, dimension]) => `<div class="mb-3">
        <div class="flex items-center justify-between">
          <span class="font-medium">${DIMENSION_LABELS[name] || name}</span>
          <span class="text-xs text-slate-500">${dimension.score} / 100</span>
        </div>
        <div class="mt-1 h-1.5 rounded bg-slate-100">
          <div class="h-1.5 rounded bg-slate-700" style="width:${dimension.score}%"></div>
        </div>
        <p class="mt-1 text-xs text-slate-600">${escapeHtml(dimension.comment)}</p>
      </div>`,
    )
    .join('');

  return card(
    'AI 評測報告',
    `<p class="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">${escapeHtml(report.advisory_notice)}</p>
     ${dimensions}
     <p class="text-xs text-slate-500">
       測資通過比例：${report.test_pass_ratio ?? '—'}｜模型：${escapeHtml(report.model_id || '—')}｜第 ${report.attempt_no} 次評測
     </p>`,
  );
}

function decisionCard(detail) {
  const history = detail.decisions
    .map(
      (decision) => `<li class="border-t border-slate-100 py-2">
        <span class="text-xs text-slate-500">修訂 ${decision.revision_no}</span>
        ｜${DECISION_LABELS[decision.result] || decision.result}
        <div class="text-xs text-slate-600 whitespace-pre-wrap">${escapeHtml(decision.internal_comment || '')}</div>
      </li>`,
    )
    .join('');

  const section = card(
    '最終決策',
    `<form id="decision-form" class="space-y-3">
       <label class="block">結果
         <select name="result" class="mt-1 w-full rounded border border-slate-300 p-2">
           <option value="">— 請選擇 —</option>
           <option value="PASS">通過</option>
           <option value="SECOND_ROUND">二輪面試</option>
           <option value="FAIL">不通過</option>
         </select>
       </label>
       <label class="block">內部評語<span class="ml-1 text-xs text-slate-500">僅同部門主管可見，HR 無法讀取</span>
         <textarea name="internal_comment" rows="4" class="mt-1 w-full rounded border border-slate-300 p-2"></textarea>
       </label>
       <p id="decision-error" class="hidden text-xs text-red-600"></p>
       <button type="submit" class="rounded bg-slate-900 px-4 py-2 text-white">送出決策</button>
     </form>
     ${detail.decisions.length ? `<ul class="mt-4">${history}</ul>` : ''}`,
  );

  section.querySelector('#decision-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const errorBox = section.querySelector('#decision-error');
    if (!form.get('result')) {
      errorBox.classList.remove('hidden');
      errorBox.textContent = '請選擇決策結果。';
      return;
    }
    try {
      await manager.recordDecision(selectedId, {
        result: form.get('result'),
        internal_comment: form.get('internal_comment') || null,
      });
      await loadAssessments();
      select(selectedId);
    } catch (error) {
      errorBox.classList.remove('hidden');
      errorBox.textContent =
        error instanceof ApiError ? error.message : '決策送出失敗，請稍後再試。';
    }
  });

  return section;
}

document.addEventListener('click', async (event) => {
  if (event.target?.id !== 'btn-reevaluate') return;
  try {
    await manager.reevaluate(selectedId);
    window.setTimeout(() => select(selectedId), 1500);
  } catch (error) {
    reportError(error);
  }
});

// ── 工具 ──────────────────────────────────────────────────────────────

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

function reportError(error) {
  // 權杖過期就回登入頁；以前這裡只能 alert「請先登入」，因為還沒有登入頁
  if (error instanceof ApiError && handleAuthFailure(error.status)) return;
  window.alert(error instanceof ApiError ? error.message : '操作失敗，請稍後再試。');
}

if (requireSession()) loadQuestionBank().then(loadAssessments);
