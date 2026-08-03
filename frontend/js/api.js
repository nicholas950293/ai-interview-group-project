// 對後端 API 的唯一呼叫點。
//
// 前端不直連 Supabase——所有資料存取一律經由 FastAPI（research.md R-002）。
// 這個檔案是那條規則在前端的強制點：其他模組不得自行發出 fetch。

const API_BASE = '/api';
const TOKEN_KEY = 'recruitment.jwt';

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getAuthToken() {
  return window.localStorage.getItem(TOKEN_KEY) || '';
}

export function setAuthToken(token) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function request(method, path, { body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const code = payload?.code || 'UNKNOWN';
    const message = payload?.message || `請求失敗（HTTP ${response.status}）`;
    throw new ApiError(response.status, code, message);
  }
  return payload;
}

function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

// ── 系統資訊（不需認證）────────────────────────────────────────────────
export const system = {
  health: () => request('GET', '/health', { auth: false }),
};

// ── 登入（尚未持有權杖，故不帶 Authorization）──────────────────────────
export const auth = {
  login: (email, password) =>
    request('POST', '/auth/login', { body: { email, password }, auth: false }),
};

// ── HR ────────────────────────────────────────────────────────────────
export const hr = {
  listDepartments: () => request('GET', '/hr/departments'),
  listAssessments: (filters) => request('GET', `/hr/assessments${qs(filters)}`),
  createAssessment: (payload) => request('POST', '/hr/assessments', { body: payload }),
  reassignManager: (id, managerId) =>
    request('POST', `/hr/assessments/${id}/reassign-manager`, { body: { manager_id: managerId } }),
  regenerateToken: (id) => request('POST', `/hr/assessments/${id}/regenerate-token`),
  previewNotification: (id) => request('POST', `/hr/assessments/${id}/notification/preview`),
  sendNotification: (id, subject, body) =>
    request('POST', `/hr/assessments/${id}/notification/send`, { body: { subject, body } }),
};

// ── 主管 ──────────────────────────────────────────────────────────────
export const manager = {
  listAssessments: () => request('GET', '/manager/assessments'),
  getAssessment: (id) => request('GET', `/manager/assessments/${id}`),
  listQuestions: () => request('GET', '/manager/questions'),
  generateQuestion: (payload) => request('POST', '/manager/questions/ai-generate', { body: payload }),
  assignQuestion: (id, question) =>
    request('POST', `/manager/assessments/${id}/assign-question`, { body: { question } }),
  recordDecision: (id, payload) =>
    request('POST', `/manager/assessments/${id}/decision`, { body: payload }),
  reevaluate: (id) => request('POST', `/manager/assessments/${id}/reevaluate`),
};

// ── 應徵者（無需認證，token 即憑證）───────────────────────────────────
export const candidate = {
  getSession: (token) => request('GET', `/candidate/session/${token}`, { auth: false }),
  run: (token, payload) =>
    request('POST', `/candidate/session/${token}/run`, { body: payload, auth: false }),
  chat: (token, message) =>
    request('POST', `/candidate/session/${token}/chat`, { body: { message }, auth: false }),
  submit: (token, answer, language) =>
    request('POST', `/candidate/session/${token}/submit`, {
      body: { answer, language },
      auth: false,
    }),
};

export const STATUS_LABELS = {
  PENDING_ASSIGN: '待指派題目',
  PENDING_CANDIDATE: '待應徵者作答',
  COMPLETED_AWAITING_REVIEW: '待主管審核',
  DECIDED: '已決策',
  EXPIRED: '已逾期',
};

export const DECISION_LABELS = {
  PASS: '通過',
  SECOND_ROUND: '二輪面試',
  FAIL: '不通過',
};

export const EMAIL_STATUS_LABELS = {
  NOT_SENT: '未寄送',
  SENT: '已寄送',
  FAILED: '寄送失敗',
};

export function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-TW', { hour12: false });
}
