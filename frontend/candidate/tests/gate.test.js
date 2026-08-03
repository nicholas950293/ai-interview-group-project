// T006：畫面狀態判定（FR-108～FR-111、FR-121、FR-126）。
//
// 涵蓋 spec.md US1 驗收情境 1～7 與 US4 情境 5～6。
// 這裡是應徵者看到什麼畫面的唯一決定點，因此測試以「情境 → 狀態」逐條對照。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  GateState,
  gateFromToken,
  gateFromSession,
  gateFromError,
  isTerminal,
} from '../core/gate.js';

const stamp = (value) => `[${value}]`; // 可預測的假格式化器，避免測試依賴地區設定

// ── gateFromToken（US1 情境 1、FR-111）────────────────────────────────

test('缺少 token 時判定為連結不完整', () => {
  for (const value of ['', '   ', null, undefined]) {
    const gate = gateFromToken(value);
    assert.equal(gate.state, GateState.LINK_INCOMPLETE);
    assert.ok(gate.message);
  }
});

test('token 存在時不產生任何終端狀態，呼叫端才會發出請求', () => {
  assert.equal(gateFromToken('a-valid-looking-value'), null);
});

// ── gateFromSession（US1 情境 2、5、6）────────────────────────────────

test('待作答的 session 判定為可作答', () => {
  const gate = gateFromSession({ status: 'PENDING_CANDIDATE', submitted_at: null });
  assert.equal(gate.state, GateState.READY);
});

test('未指派題目判定為題目準備中，而非空白頁（US1 情境 5）', () => {
  const gate = gateFromSession({ status: 'PENDING_ASSIGN', question: null });
  assert.equal(gate.state, GateState.PREPARING);
  assert.ok(gate.message);
});

test('已提交判定為已提交，並在訊息中呈現提交時間（US1 情境 6）', () => {
  const gate = gateFromSession(
    { status: 'COMPLETED_AWAITING_REVIEW', submitted_at: '2026-08-01T02:00:00Z' },
    { formatDate: stamp },
  );
  assert.equal(gate.state, GateState.SUBMITTED);
  assert.match(gate.message, /\[2026-08-01T02:00:00Z\]/);
});

test('後端若回傳 EXPIRED 狀態，即使是 200 也判定為逾期', () => {
  const gate = gateFromSession({ status: 'EXPIRED' });
  assert.equal(gate.state, GateState.EXPIRED);
});

test('題目準備中優先於其他判定——此時沒有題目可顯示', () => {
  const gate = gateFromSession({ status: 'PENDING_ASSIGN', submitted_at: null });
  assert.equal(gate.state, GateState.PREPARING);
});

// ── gateFromError（US1 情境 3、4、7；US4 情境 5、6）──────────────────

test('410 判定為逾期，訊息含聯繫 HR 的指引（US1 情境 3）', () => {
  const gate = gateFromError({ status: 410, message: '後端訊息' });
  assert.equal(gate.state, GateState.EXPIRED);
  assert.match(gate.message, /HR/);
});

test('404 判定為找不到連結（US1 情境 4）', () => {
  const gate = gateFromError({ status: 404 });
  assert.equal(gate.state, GateState.NOT_FOUND);
});

test('409 判定為已提交（US4 情境 5、FR-121、FR-126）', () => {
  const gate = gateFromError({ status: 409 });
  assert.equal(gate.state, GateState.SUBMITTED);
});

test('其餘狀態碼與非 API 例外一律判定為載入失敗（US1 情境 7）', () => {
  for (const error of [{ status: 500 }, { status: 0 }, new Error('network down'), null]) {
    assert.equal(gateFromError(error).state, GateState.LOAD_FAILED);
  }
});

test('錯誤訊息一律來自本地字串表，不回放後端內容（FR-134）', () => {
  const gate = gateFromError({ status: 404, message: 'token=abc123 不存在' });
  assert.ok(!gate.message.includes('abc123'));
});

// ── isTerminal（FR-110）──────────────────────────────────────────────

test('READY 以外的狀態皆為終端狀態，工作區必須保持隱藏', () => {
  assert.equal(isTerminal(GateState.READY), false);
  for (const state of Object.values(GateState)) {
    if (state === GateState.READY) continue;
    assert.equal(isTerminal(state), true, `${state} 應為終端狀態`);
  }
});
