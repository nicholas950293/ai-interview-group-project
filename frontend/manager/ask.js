// 面試官出題頁的組裝點。
//
// 這頁沒有自己的後端：送出走的是既有的
// POST /manager/assessments/{id}/assign-question，與完整主管介面同一個端點。
// 因此題目會被寫成 question_snapshot、狀態由「待指派題目」轉為「待應徵者作答」、
// 並留下 QUESTION_ASSIGNED 稽核紀錄——應徵者作答頁不需要任何修改就會看到題目。
//
// 唯一的判斷邏輯（一段文字 → Question）在 core/question-draft.js，可獨立測試。

import { manager, clearAuthToken, ApiError } from '../js/api.js';
import { requireSession, handleAuthFailure, getProfile, goToLogin } from '../js/session.js';
import { buildQuestion } from './core/question-draft.js';
import { describeLoadFailure, NETWORK_ERROR } from './core/errors.js';

const el = (id) => document.getElementById(id);

const dom = {
  askPanel: el('ask-panel'),
  askForm: el('ask-form'),
  askMeta: el('ask-meta'),
  askError: el('ask-error'),
  askResult: el('ask-result'),
  who: el('who'),
  logout: el('btn-logout'),
  sendButton: el('btn-send'),
  assessmentSelect: el('assessment-select'),
  assessmentHint: el('assessment-hint'),
  questionInput: el('question-input'),
  caseStdin: el('case-stdin'),
  caseStdout: el('case-stdout'),
};

const MESSAGES = {
  NO_PENDING:
    '你的部門目前沒有「待指派題目」的應徵者。只有這個狀態的考核能收題目——'
    + '請先由 HR 建立考核（主管只看得到自己部門的考核）。',
};

let busy = false;

/** ApiError → HTTP 狀態碼；連線失敗等非 API 例外一律視為網路問題。 */
function statusOf(error) {
  return error instanceof ApiError ? error.status : NETWORK_ERROR;
}

// ── 畫面切換 ──────────────────────────────────────────────────────────

function setVisible(element, visible) {
  element.hidden = !visible;
  element.classList.toggle('hidden', !visible);
}

function showError(message) {
  dom.askError.textContent = message;
  setVisible(dom.askError, true);
}

function clearError() {
  setVisible(dom.askError, false);
}

function showResult(message, level = 'info') {
  dom.askResult.className = `notice notice--${level}`;
  dom.askResult.textContent = message;
  dom.askResult.hidden = false;
}

// ── 應徵者清單 ────────────────────────────────────────────────────────

function describe(assessment) {
  return `${assessment.name}｜${assessment.job_title}（${assessment.dept_id}）`;
}

function fillAssessments(pending) {
  dom.assessmentSelect.replaceChildren(
    ...pending.map((assessment) => {
      const option = document.createElement('option');
      option.value = assessment.id;
      option.textContent = describe(assessment);
      return option;
    }),
  );

  const hasTargets = pending.length > 0;
  dom.assessmentSelect.disabled = !hasTargets;
  dom.sendButton.disabled = !hasTargets;
  dom.askMeta.textContent = hasTargets ? `${pending.length} 位待指派` : '';

  // 寫進 #assessment-hint 而非 #ask-result：送出成功後清單通常就空了，
  // 若共用同一個位置，成功訊息會立刻被這句蓋掉，讀起來像送出失敗。
  dom.assessmentHint.textContent = hasTargets ? '' : MESSAGES.NO_PENDING;
  setVisible(dom.assessmentHint, !hasTargets);
}

async function loadAssessments() {
  let assessments;
  try {
    assessments = await manager.listAssessments();
  } catch (error) {
    const status = statusOf(error);
    // 權杖過期就重新登入；其餘（網址錯、後端沒開）重新登入也解決不了
    if (handleAuthFailure(status)) return;
    return showResult(describeLoadFailure(status, error?.message), 'error');
  }

  setVisible(dom.askPanel, true);
  // 只有「待指派題目」的考核能收題目，其餘狀態送出會被後端以 409 擋下
  fillAssessments(assessments.filter((item) => item.status === 'PENDING_ASSIGN'));
}

// ── 送出 ──────────────────────────────────────────────────────────────

dom.logout.addEventListener('click', () => {
  clearAuthToken();
  goToLogin();
});

dom.askForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return; // 指派會改變考核狀態，重複送出的第二次必定拿到 409

  clearError();
  const draft = buildQuestion({
    text: dom.questionInput.value,
    stdin: dom.caseStdin.value,
    expectedStdout: dom.caseStdout.value,
  });
  if (!draft.ok) return showError(draft.error);

  const assessmentId = dom.assessmentSelect.value;
  const target = dom.assessmentSelect.selectedOptions[0]?.textContent || '';

  busy = true;
  dom.sendButton.disabled = true;
  try {
    await manager.assignQuestion(assessmentId, draft.question);
    dom.askForm.reset();
    // 先重載清單再顯示結果——反過來的話，清單重載時的空狀態會蓋掉成功訊息
    await loadAssessments();
    showResult(
      `✓ 題目已送給 ${target}。該筆考核轉為「待應徵者作答」，`
      + '應徵者開啟原本的專屬連結就會看到這道題目。',
      'success',
    );
  } catch (error) {
    // 後端訊息在這裡是有價值的：缺測資、狀態不符都會回傳可行動的說明
    showError(describeLoadFailure(statusOf(error), error?.message));
  } finally {
    busy = false;
    dom.sendButton.disabled = false;
  }
});

// ── 啟動 ──────────────────────────────────────────────────────────────

if (requireSession()) {
  const profile = getProfile();
  if (profile) dom.who.textContent = `${profile.name}｜${profile.deptId || '全公司'}`;
  loadAssessments();
}

// 標記模組已成功載入；HTML 的保險腳本以此判斷頁面是否正常
window.__pageReady = true;
