// 應徵者作答頁的組裝點（FR-104、FR-111）。
//
// 這是本模組唯一接觸 API 的檔案：ui/ 底下的模組全部以 callback 取得資料，
// 因此「所有後端存取都經由 frontend/js/api.js」這條規則在這裡有單一強制點，
// 而 ui/ 的每個檔案都能被單獨閱讀而不必追它去打了哪些請求。
//
// 這裡也不做任何判定——狀態由 core/gate.js 決定，呈現內容由 core/ 的其餘模組
// 決定。main.js 只負責把兩邊接起來。

import { candidate, formatDate } from '../js/api.js';

import {
  GateState,
  gateFromToken,
  gateFromSession,
  gateFromError,
  isTerminal,
} from './core/gate.js';
import { toSessionView } from './core/session-view.js';
import {
  formatRunOutput,
  formatRunMeta,
  afterTrialRun,
  resolveRunFailure,
  UNCHANGED,
} from './core/run-result.js';
import {
  RUN_MESSAGES,
  SUBMIT_MESSAGES,
  expiresAtLabel,
  submitSuccessMessage,
} from './core/messages.js';

import { collectElements } from './ui/elements.js';
import { showNotice, hideNotice } from './ui/notice.js';
import { renderQuestion } from './ui/question.js';
import { createAnswerPanel } from './ui/answer.js';
import { createChatPanel } from './ui/chat.js';

const token = new URLSearchParams(window.location.search).get('token') || '';
const dom = collectElements();

const state = { trialRunsRemaining: 0 };
let panel = null;

// ── 畫面切換 ──────────────────────────────────────────────────────────

function setVisible(element, visible) {
  element.hidden = !visible;
  element.classList.toggle('hidden', !visible);
}

/** 終端狀態一律隱藏工作區，題目內容不再顯示（FR-110）。
 *
 * 頁首的提交鈕與「作答中」標示也必須一起收掉：它們在頁首而不在工作區內，
 * 若只隱藏工作區，逾期或已提交的應徵者會看到一顆按了必定失敗的提交鈕。 */
function applyGate(gate) {
  setVisible(dom.workspace, false);
  setVisible(dom.topbarActions, false);
  setVisible(dom.topbarMeta, false);
  showNotice(dom.notice, gate);
}

function showSubmitError(message) {
  dom.submitError.textContent = message;
  setVisible(dom.submitError, true);
}

// ── 試跑與提交 ────────────────────────────────────────────────────────

async function handleRun(payload) {
  panel.showRunOutput(RUN_MESSAGES.RUNNING, '');

  try {
    const result = await candidate.run(token, payload);
    panel.showRunOutput(formatRunOutput(result), formatRunMeta(result));
    state.trialRunsRemaining = afterTrialRun(state.trialRunsRemaining);
    panel.setTrialRunsRemaining(state.trialRunsRemaining);
  } catch (error) {
    const outcome = resolveRunFailure(error);
    // 409／410 代表這次考核已經結束，整個畫面必須離開可作答狀態（FR-121）
    if (outcome.gate) return applyGate(gateFromError(error));

    if (outcome.trialRunsRemaining !== UNCHANGED) {
      state.trialRunsRemaining = outcome.trialRunsRemaining;
      panel.setTrialRunsRemaining(state.trialRunsRemaining);
    }
    panel.showRunOutput(outcome.output, '');
  }
}

async function handleSubmit({ answer, language }) {
  try {
    const result = await candidate.submit(token, answer, language);
    // 提交完成必須顯示明確的成功確認（FR-125）
    applyGate({
      state: GateState.SUBMITTED,
      message: submitSuccessMessage(formatDate(result.submitted_at)),
    });
  } catch (error) {
    const gate = gateFromError(error);
    // 409／410 轉入終端狀態；其餘保留作答內容讓應徵者重試（FR-126）
    if (gate.state === GateState.LOAD_FAILED) showSubmitError(SUBMIT_MESSAGES.FAILED);
    else applyGate(gate);
  }
}

// ── 渲染 ──────────────────────────────────────────────────────────────

function render(view) {
  hideNotice(dom.notice);
  setVisible(dom.workspace, true);

  // 頁首已有「線上測驗」品牌標示，此處只放職缺名稱（設計稿的頁首分區）
  dom.jobTitle.textContent = view.jobTitle;
  dom.expiresAt.textContent = expiresAtLabel(formatDate(view.expiresAt));

  renderQuestion(dom.question, view.question);

  state.trialRunsRemaining = view.trialRunsRemaining;
  panel = createAnswerPanel({
    elements: dom.answer,
    view,
    onRun: handleRun,
    onSubmit: handleSubmit,
  });

  const chat = createChatPanel({
    ...dom.chat,
    onSend: (message) => candidate.chat(token, message),
  });
  // 重新整理後對話不該消失——後端本來就把歷程放在 session 裡（FR-128）
  chat.restore(view.chatHistory);
}

// ── 啟動 ──────────────────────────────────────────────────────────────

async function boot() {
  // 連結不完整時不得發出任何請求（FR-111）
  const blocked = gateFromToken(token);
  if (blocked) return applyGate(blocked);

  let session;
  try {
    session = await candidate.getSession(token);
  } catch (error) {
    return applyGate(gateFromError(error));
  }

  const gate = gateFromSession(session, { formatDate });
  if (isTerminal(gate.state)) return applyGate(gate);

  render(toSessionView(session));
}

boot();
