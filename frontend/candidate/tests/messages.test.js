// T004：面向應徵者的字串必須有單一來源（FR-108、FR-134）。
//
// 這份測試看起來瑣碎，但它守的是一件具體的事：訊息一旦散落在各個 ui 模組裡，
// 「不得把 token 寫進畫面」這種規則就沒有可稽核的位置。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  NOTICE_MESSAGES,
  RUN_MESSAGES,
  CHAT_MESSAGES,
  SUBMIT_MESSAGES,
  TERMINATION_LABELS,
  submittedMessage,
  submitSuccessMessage,
  trialRemainingLabel,
  expiresAtLabel,
} from '../core/messages.js';
import { GateState } from '../core/gate.js';

const ALL_TABLES = {
  NOTICE_MESSAGES,
  RUN_MESSAGES,
  CHAT_MESSAGES,
  SUBMIT_MESSAGES,
  TERMINATION_LABELS,
};

test('每個非 READY 的畫面狀態都有對應訊息', () => {
  for (const state of Object.values(GateState)) {
    if (state === GateState.READY) continue;
    assert.ok(NOTICE_MESSAGES[state], `缺少 ${state} 的訊息`);
  }
});

test('READY 沒有提示訊息——它顯示的是作答工作區', () => {
  assert.equal(NOTICE_MESSAGES[GateState.READY], undefined);
});

test('所有訊息皆為非空字串', () => {
  for (const [tableName, table] of Object.entries(ALL_TABLES)) {
    for (const [key, value] of Object.entries(table)) {
      assert.equal(typeof value, 'string', `${tableName}.${key} 不是字串`);
      assert.ok(value.trim().length > 0, `${tableName}.${key} 為空`);
    }
  }
});

test('訊息不含 token、未替換的樣板佔位符或原始例外字樣（FR-134）', () => {
  for (const [tableName, table] of Object.entries(ALL_TABLES)) {
    for (const [key, value] of Object.entries(table)) {
      const label = `${tableName}.${key}`;
      assert.ok(!/token/i.test(value), `${label} 含 token 字樣`);
      assert.ok(!value.includes('${'), `${label} 含未替換的佔位符`);
      assert.ok(!/undefined|\[object/.test(value), `${label} 含未處理的值`);
    }
  }
});

test('沙箱不可用與次數上限的訊息都明確告知仍可提交（FR-119、FR-120）', () => {
  assert.match(RUN_MESSAGES.SANDBOX_UNAVAILABLE, /提交/);
  assert.match(RUN_MESSAGES.LIMIT_REACHED, /提交/);
});

test('助教故障訊息明確告知作答不受影響（FR-129）', () => {
  assert.match(CHAT_MESSAGES.UNAVAILABLE, /作答/);
  assert.match(CHAT_MESSAGES.FAILED, /作答/);
});

test('提交確認訊息明確告知不可修改（FR-123）', () => {
  assert.match(SUBMIT_MESSAGES.CONFIRM_BODY, /無法修改|不可修改/);
});

test('帶時間的訊息會把時間嵌入輸出', () => {
  assert.match(submittedMessage('2026-08-01 10:00'), /2026-08-01 10:00/);
  assert.match(submitSuccessMessage('2026-08-01 10:00'), /2026-08-01 10:00/);
});

test('剩餘次數與到期時間的標籤含其數值', () => {
  assert.match(trialRemainingLabel(7), /7/);
  assert.match(expiresAtLabel('2026-08-10 09:00'), /2026-08-10 09:00/);
});

test('終止原因涵蓋沙箱契約的全部代碼', () => {
  for (const reason of [
    'COMPLETED',
    'TIMEOUT',
    'MEMORY_LIMIT',
    'PIDS_LIMIT',
    'OUTPUT_LIMIT',
    'COMPILE_ERROR',
    'SANDBOX_UNAVAILABLE',
  ]) {
    assert.ok(TERMINATION_LABELS[reason], `缺少 ${reason} 的中文說明`);
  }
});
