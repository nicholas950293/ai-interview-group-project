// 面試官出題頁的唯一判斷邏輯：一段文字 → 後端要的 Question。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  buildQuestion,
  DRAFT_ERRORS,
  DEFAULT_DIFFICULTY,
  MAX_TITLE_LENGTH,
} from '../core/question-draft.js';

test('第一行成為標題，其餘成為敘述', () => {
  const result = buildQuestion({ text: '實作 LRU 快取\n\n請支援 get 與 put，皆為 O(1)。' });
  assert.equal(result.ok, true);
  assert.equal(result.question.title, '實作 LRU 快取');
  assert.equal(result.question.description, '請支援 get 與 put，皆為 O(1)。');
});

test('只有一行時，標題與敘述相同——後端要求 description 非空', () => {
  const result = buildQuestion({ text: '寫一個函式回傳兩數之和' });
  assert.equal(result.question.title, '寫一個函式回傳兩數之和');
  assert.equal(result.question.description, '寫一個函式回傳兩數之和');
});

test('難度使用預設值，且不謊報題目來源與語言', () => {
  const { question } = buildQuestion({ text: '題目' });
  assert.equal(question.difficulty, DEFAULT_DIFFICULTY);
  assert.equal(question.source, undefined);
  assert.equal(question.language, undefined);
});

test('標題超過長度上限時截斷，避免後端以 422 退回', () => {
  const { question } = buildQuestion({ text: 'A'.repeat(MAX_TITLE_LENGTH + 50) });
  assert.equal(question.title.length, MAX_TITLE_LENGTH);
});

test('空白輸入被擋下，不送出請求', () => {
  for (const text of ['', '   ', '\n\n', undefined, null]) {
    const result = buildQuestion({ text });
    assert.equal(result.ok, false);
    assert.equal(result.error, DRAFT_ERRORS.EMPTY);
  }
});

test('開頭的空行被略過，第一個有內容的行成為標題', () => {
  const result = buildQuestion({ text: '   \n\n真正的標題\n內容' });
  assert.equal(result.ok, true);
  assert.equal(result.question.title, '真正的標題');
  assert.equal(result.question.description, '內容');
});

test('前後多餘空白不影響結果', () => {
  const { question } = buildQuestion({ text: '\n\n  標題  \n內容\n\n  ' });
  assert.equal(question.title, '標題');
  assert.equal(question.description, '內容');
});

// ── 測資（FR-026）────────────────────────────────────────────────────

test('兩欄皆空時不產生測資——非工程類不需要，工程類由後端擋', () => {
  const { question } = buildQuestion({ text: '題目', stdin: '  ', expectedStdout: '' });
  assert.deepEqual(question.test_cases, []);
});

test('填了測資就帶上，且標示為非隱藏（應徵者看得到範例）', () => {
  const { question } = buildQuestion({
    text: '題目',
    stdin: '3 5\n',
    expectedStdout: '8\n',
  });
  assert.equal(question.test_cases.length, 1);
  assert.equal(question.test_cases[0].stdin, '3 5\n');
  assert.equal(question.test_cases[0].expected_stdout, '8\n');
  assert.equal(question.test_cases[0].is_hidden, false);
});

test('只填其中一欄仍產生測資——後端只擋兩欄皆空的情況', () => {
  assert.equal(buildQuestion({ text: '題目', stdin: '3 5' }).question.test_cases.length, 1);
  assert.equal(
    buildQuestion({ text: '題目', expectedStdout: '8' }).question.test_cases.length,
    1,
  );
});

test('測資內容原樣送出，不做修剪——尾端換行對比對有意義', () => {
  const { question } = buildQuestion({ text: '題目', stdin: ' 3 5 \n', expectedStdout: '8\n' });
  assert.equal(question.test_cases[0].stdin, ' 3 5 \n');
});
