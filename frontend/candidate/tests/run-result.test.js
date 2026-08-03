// T010：試跑結果與次數推進（FR-117～FR-122）。
//
// 涵蓋 spec.md US2 驗收情境 4～9。試跑的失敗分支比成功分支多，
// 而「503 不得扣次數」「429 要歸零但不擋提交」這兩條最容易寫錯，因此逐條釘住。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  describeTermination,
  formatRunOutput,
  formatRunMeta,
  afterTrialRun,
  canRun,
  resolveRunFailure,
  UNCHANGED,
} from '../core/run-result.js';
import { GateState } from '../core/gate.js';

const completed = {
  stdout: '8\n',
  stderr: '',
  exit_code: 0,
  duration_ms: 42,
  termination_reason: 'COMPLETED',
};

// ── 輸出與中繼資訊（US2 情境 4、5）──────────────────────────────────

test('標準輸出與錯誤輸出一併呈現', () => {
  assert.equal(formatRunOutput(completed), '8\n');
  assert.equal(
    formatRunOutput({ ...completed, stderr: 'warning: 未使用的變數' }),
    '8\n\nwarning: 未使用的變數',
  );
});

test('沒有任何輸出時給出明確的佔位文字，而非空白區塊', () => {
  const output = formatRunOutput({ ...completed, stdout: '', stderr: '' });
  assert.ok(output.trim().length > 0);
});

test('中繼資訊含終止原因的中文說明與耗時', () => {
  const meta = formatRunMeta(completed);
  assert.match(meta, /執行完成/);
  assert.match(meta, /42/);
});

test('輸出被截斷時明確標示（FR-117）', () => {
  assert.match(formatRunMeta({ ...completed, truncated: true }), /截斷/);
  assert.ok(!/截斷/.test(formatRunMeta(completed)));
});

test('編譯錯誤呈現為編譯／語法錯誤，而非系統故障（US2 情境 5）', () => {
  const compileError = {
    stdout: '',
    stderr: 'syntax error: unexpected }',
    exit_code: null,
    duration_ms: 12,
    termination_reason: 'COMPILE_ERROR',
  };
  assert.match(describeTermination('COMPILE_ERROR'), /編譯|語法/);
  assert.match(formatRunOutput(compileError), /syntax error/);
  assert.ok(!/系統/.test(formatRunMeta(compileError)));
});

test('逾時與資源上限皆有中文說明', () => {
  assert.match(describeTermination('TIMEOUT'), /逾時/);
  assert.match(describeTermination('MEMORY_LIMIT'), /記憶體/);
});

test('未知的終止原因原樣呈現，不顯示 undefined', () => {
  assert.equal(describeTermination('SOMETHING_NEW'), 'SOMETHING_NEW');
  assert.ok(!/undefined/.test(describeTermination(undefined)));
});

// ── 次數推進（US2 情境 6、7）────────────────────────────────────────

test('試跑成功後剩餘次數減一', () => {
  assert.equal(afterTrialRun(17), 16);
  assert.equal(afterTrialRun(1), 0);
});

test('剩餘次數不會低於零', () => {
  assert.equal(afterTrialRun(0), 0);
  assert.equal(afterTrialRun(-3), 0);
});

test('次數為零時不可試跑，仍可提交——提交不受次數影響', () => {
  assert.equal(canRun(1), true);
  assert.equal(canRun(0), false);
});

// ── 失敗分支（US2 情境 8、9；FR-119～FR-121）─────────────────────────

test('429：次數歸零，畫面不轉換，仍可提交（US2 情境 8）', () => {
  const outcome = resolveRunFailure({ status: 429 });
  assert.equal(outcome.trialRunsRemaining, 0);
  assert.equal(outcome.gate, null);
  assert.match(outcome.output, /提交/);
});

test('503：不得扣減次數，且明確告知仍可提交（US2 情境 9、FR-120）', () => {
  const outcome = resolveRunFailure({ status: 503 });
  assert.equal(outcome.trialRunsRemaining, UNCHANGED);
  assert.equal(outcome.gate, null);
  assert.match(outcome.output, /提交/);
});

test('409：畫面轉為已提交（FR-121）', () => {
  const outcome = resolveRunFailure({ status: 409 });
  assert.equal(outcome.gate, GateState.SUBMITTED);
  assert.equal(outcome.trialRunsRemaining, UNCHANGED);
});

test('410：畫面轉為逾期（FR-121）', () => {
  assert.equal(resolveRunFailure({ status: 410 }).gate, GateState.EXPIRED);
});

test('其餘失敗顯示一般性錯誤，不轉換畫面、不扣次數', () => {
  for (const error of [{ status: 500 }, new Error('network down'), null]) {
    const outcome = resolveRunFailure(error);
    assert.equal(outcome.gate, null);
    assert.equal(outcome.trialRunsRemaining, UNCHANGED);
    assert.ok(outcome.output.trim().length > 0);
  }
});

test('失敗訊息不回放後端原文，避免夾帶未預期內容（FR-134）', () => {
  const outcome = resolveRunFailure({ status: 500, message: 'token=abc123 internal trace' });
  assert.ok(!outcome.output.includes('abc123'));
});
