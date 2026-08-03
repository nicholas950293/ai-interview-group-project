// 面試官出題頁的組裝點。
//
// 這頁沒有自己的後端：送出走的是既有的
// POST /manager/assessments/{id}/assign-question，與完整主管介面同一個端點。
// 因此題目會被寫成 question_snapshot、狀態由「待指派題目」轉為「待應徵者作答」、
// 並留下 QUESTION_ASSIGNED 稽核紀錄——應徵者作答頁不需要任何修改就會看到題目。
//
// 唯一的判斷邏輯（一段文字 → Question）在 core/question-draft.js，可獨立測試。

import { manager, getAuthToken, setAuthToken, ApiError } from '../js/api.js';
import { buildQuestion } from './core/question-draft.js';
import { describeLoadFailure, isAuthFailure, NETWORK_ERROR } from './core/errors.js';

const el = (id) => document.getElementById(id);

const dom = {
  authPanel: el('auth-panel'),
  authForm: el('auth-form'),
  authToken: el('auth-token'),
  askPanel: el('ask-panel'),
  askForm: el('ask-form'),
  askMeta: el('ask-meta'),
  askError: el('ask-error'),
  askResult: el('ask-result'),
  sendButton: el('btn-send'),
  assessmentSelect: el('assessment-select'),
  questionInput: el('question-input'),
  caseStdin: el('case-stdin'),
  caseStdout: el('case-stdout'),
};

const MESSAGES = {
  NO_PENDING:
    '目前沒有「待指派題目」的應徵者。只有這個狀態的考核能收題目——'
    + '請先由 HR 建立考核，或確認你的權杖對應的部門正確（主管只看得到自己部門的考核）。',
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

function showAuth(message) {
  setVisible(dom.askPanel, false);
  setVisible(dom.authPanel, true);
  if (message) showResult(message, 'error');
  dom.authToken.focus();
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
  if (!hasTargets) showResult(MESSAGES.NO_PENDING, 'warn');
}

async function loadAssessments() {
  let assessments;
  try {
    assessments = await manager.listAssessments();
  } catch (error) {
    const status = statusOf(error);
    const message = describeLoadFailure(status, error?.message);
    // 權杖問題才退回輸入畫面；其餘（網址錯、後端沒開）重貼權杖也解決不了
    if (isAuthFailure(status)) return showAuth(message);
    return showResult(message, 'error');
  }

  setVisible(dom.authPanel, false);
  setVisible(dom.askPanel, true);
  // 只有「待指派題目」的考核能收題目，其餘狀態送出會被後端以 409 擋下
  fillAssessments(assessments.filter((item) => item.status === 'PENDING_ASSIGN'));
}

// ── 送出 ──────────────────────────────────────────────────────────────

dom.authForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const token = dom.authToken.value.trim();
  if (!token) return;
  setAuthToken(token);
  dom.askResult.hidden = true;
  await loadAssessments();
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
    showResult(
      `已送出給 ${target}。該筆考核轉為「待應徵者作答」，`
      + '應徵者開啟原本的專屬連結就會看到這道題目。',
      'info',
    );
    dom.askForm.reset();
    await loadAssessments();
  } catch (error) {
    // 後端訊息在這裡是有價值的：缺測資、狀態不符都會回傳可行動的說明
    showError(describeLoadFailure(statusOf(error), error?.message));
  } finally {
    busy = false;
    dom.sendButton.disabled = false;
  }
});

// ── 啟動 ──────────────────────────────────────────────────────────────

if (getAuthToken()) loadAssessments();
else showAuth();
