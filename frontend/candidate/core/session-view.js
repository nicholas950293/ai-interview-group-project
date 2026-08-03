// session 回應 → 畫面用的視圖模型（FR-132、FR-133）。
//
// 這裡採「白名單投影」而非「直接攤開 session」：每個要顯示的欄位都必須在本檔
// 明確寫出來。代價是後端新增欄位時要同步改這裡，換來的是後端若不慎多回傳了
// AI 報告、內部評語或隱藏測資，前端也不可能把它渲染出去——這條保證不需要
// 每次改動都重新稽核一遍（tests/session-view.test.js）。

const DEFAULT_LANGUAGE = 'python';
const ALLOWED_CHAT_ROLES = new Set(['candidate', 'assistant']);

/** 視圖模型的完整鍵集合。測試以此斷言沒有欄位偷偷溜進來。 */
export const SESSION_VIEW_FIELDS = Object.freeze([
  'jobTitle',
  'expiresAt',
  'isEngineering',
  'language',
  'trialRunsRemaining',
  'question',
  'chatHistory',
]);

function text(value) {
  return typeof value === 'string' ? value : '';
}

/** 範例測資只有這三個欄位會被顯示；後端附帶的其餘欄位一律丟棄。 */
export function toSampleCase(raw) {
  const data = raw || {};
  return {
    name: text(data.name),
    stdin: text(data.stdin),
    expectedStdout: text(data.expected_stdout),
  };
}

function toChatMessage(raw) {
  const data = raw || {};
  return {
    role: data.role,
    content: text(data.content),
    guardrailTriggered: data.guardrail_triggered === true,
  };
}

function toQuestion(raw) {
  const data = raw || {};
  const cases = Array.isArray(data.sample_cases) ? data.sample_cases : [];
  return {
    title: text(data.title),
    description: text(data.description),
    constraints: text(data.constraints),
    sampleCases: cases.map(toSampleCase),
  };
}

function resolveLanguage(session, isEngineering) {
  // 非工程類沒有語言概念；提交時該欄位須為空值（US3 情境 2）
  if (!isEngineering) return null;
  const question = session.question || {};
  return question.language || session.code_language || DEFAULT_LANGUAGE;
}

export function toSessionView(session) {
  const data = session || {};
  const isEngineering = data.dept_type === 'ENGINEERING';

  return {
    jobTitle: text(data.job_title),
    expiresAt: text(data.token_expires_at),
    isEngineering,
    language: resolveLanguage(data, isEngineering),
    trialRunsRemaining: Number.isFinite(data.trial_runs_remaining)
      ? data.trial_runs_remaining
      : 0,
    question: toQuestion(data.question),
    chatHistory: (Array.isArray(data.chat_history) ? data.chat_history : [])
      .map(toChatMessage)
      .filter((message) => ALLOWED_CHAT_ROLES.has(message.role) && message.content),
  };
}
