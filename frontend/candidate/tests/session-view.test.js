// T008：白名單視圖模型（FR-132、FR-133；US3 情境 1～2）。
//
// 最關鍵的斷言是**未知欄位一律被丟棄**。應徵者頁面若採「把 session 直接攤開來渲染」
// 的寫法，後端日後多回傳一個欄位就可能變成外洩——白名單投影讓這件事不可能發生。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { toSessionView, SESSION_VIEW_FIELDS } from '../core/session-view.js';

const ENGINEERING_SESSION = {
  job_title: '後端工程師',
  dept_type: 'ENGINEERING',
  status: 'PENDING_CANDIDATE',
  token_expires_at: '2026-08-10T00:00:00Z',
  code_language: 'python',
  trial_runs_remaining: 17,
  submitted_at: null,
  question: {
    title: '兩數相加',
    description: '讀入兩個整數並輸出總和',
    constraints: '時間複雜度 O(1)',
    language: 'go',
    sample_cases: [{ name: '公開案例', stdin: '3 5\n', expected_stdout: '8\n' }],
  },
  chat_history: [
    { role: 'candidate', content: '這題在問什麼？', created_at: '2026-08-01T00:00:00Z' },
    { role: 'assistant', content: '先想想輸入格式', guardrail_triggered: true },
  ],
};

test('輸出的鍵完全等於白名單', () => {
  const view = toSessionView(ENGINEERING_SESSION);
  assert.deepEqual(Object.keys(view).sort(), [...SESSION_VIEW_FIELDS].sort());
});

test('搬運既有欄位', () => {
  const view = toSessionView(ENGINEERING_SESSION);
  assert.equal(view.jobTitle, '後端工程師');
  assert.equal(view.expiresAt, '2026-08-10T00:00:00Z');
  assert.equal(view.isEngineering, true);
  assert.equal(view.trialRunsRemaining, 17);
  assert.equal(view.question.title, '兩數相加');
  assert.equal(view.question.constraints, '時間複雜度 O(1)');
});

test('題目自帶的語言優先於考核的預設語言', () => {
  assert.equal(toSessionView(ENGINEERING_SESSION).language, 'go');
});

test('題目未指定語言時回退至考核語言，再回退至預設值', () => {
  const noQuestionLanguage = {
    ...ENGINEERING_SESSION,
    question: { ...ENGINEERING_SESSION.question, language: null },
  };
  assert.equal(toSessionView(noQuestionLanguage).language, 'python');

  const noLanguageAtAll = { ...noQuestionLanguage, code_language: null };
  assert.equal(toSessionView(noLanguageAtAll).language, 'python');
});

test('非工程類不帶語言，且被標示為非工程類（US3 情境 1～2）', () => {
  const view = toSessionView({ ...ENGINEERING_SESSION, dept_type: 'NON_ENGINEERING' });
  assert.equal(view.isEngineering, false);
  assert.equal(view.language, null);
});

test('範例測資只保留三個欄位', () => {
  const view = toSessionView(ENGINEERING_SESSION);
  assert.deepEqual(Object.keys(view.question.sampleCases[0]).sort(), [
    'expectedStdout',
    'name',
    'stdin',
  ]);
});

test('未預期的欄位一律被丟棄（FR-132、FR-133）', () => {
  const polluted = {
    ...ENGINEERING_SESSION,
    ai_report: { dimensions: { correctness: { score: 80, comment: '不得外洩' } } },
    manager_decision: { result: 'FAIL', internal_comment: '不得外洩' },
    candidate_email: 'someone@example.com',
    question: {
      ...ENGINEERING_SESSION.question,
      test_cases: [{ stdin: '隱藏輸入', expected_stdout: '隱藏輸出', is_hidden: true }],
      sample_cases: [
        {
          name: '公開案例',
          stdin: '3 5\n',
          expected_stdout: '8\n',
          is_hidden: false,
          timeout_seconds: 10,
        },
      ],
    },
  };

  const serialized = JSON.stringify(toSessionView(polluted));
  for (const leak of [
    '不得外洩',
    'someone@example.com',
    '隱藏輸入',
    '隱藏輸出',
    'is_hidden',
    'timeout_seconds',
    'dimensions',
  ]) {
    assert.ok(!serialized.includes(leak), `視圖模型洩漏了 ${leak}`);
  }
});

test('沒有題目時給出空的題目結構，而不是 undefined', () => {
  const view = toSessionView({ ...ENGINEERING_SESSION, question: null });
  assert.equal(view.question.title, '');
  assert.deepEqual(view.question.sampleCases, []);
});

test('對話歷程被還原，且只保留合法角色（FR-128）', () => {
  const view = toSessionView(ENGINEERING_SESSION);
  assert.deepEqual(
    view.chatHistory.map((item) => item.role),
    ['candidate', 'assistant'],
  );
  assert.equal(view.chatHistory[0].content, '這題在問什麼？');
  assert.equal(view.chatHistory[1].guardrailTriggered, true);
});

test('不合法的角色與缺內容的訊息被略過', () => {
  const view = toSessionView({
    ...ENGINEERING_SESSION,
    chat_history: [
      { role: 'system', content: '系統提示不得顯示' },
      { role: 'candidate', content: '' },
      { role: 'candidate', content: '正常訊息' },
    ],
  });
  assert.equal(view.chatHistory.length, 1);
  assert.equal(view.chatHistory[0].content, '正常訊息');
});

test('缺漏的欄位有安全的預設值', () => {
  const view = toSessionView({});
  assert.equal(view.jobTitle, '');
  assert.equal(view.trialRunsRemaining, 0);
  assert.deepEqual(view.chatHistory, []);
});
