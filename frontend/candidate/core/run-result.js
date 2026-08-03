// 試跑結果與失敗分支的判定（FR-117～FR-122）。
//
// 試跑的失敗路徑比成功路徑重要：429 要歸零次數但**不得**擋住提交，
// 503 要顯示訊息但**不得**扣次數，409／410 則必須把整個畫面推到終端狀態。
// 這四條規則寫在 DOM 事件處理器裡時沒有任何回歸保護，因此全部集中在這裡。

import { GateState } from './gate.js';
import { RUN_MESSAGES, TERMINATION_LABELS } from './messages.js';

/** 表示「剩餘次數不變」。用哨符而非 null，才能和「歸零」清楚區分。 */
export const UNCHANGED = Symbol('trial-runs-unchanged');

/** HTTP 狀態碼 → 失敗處置。未列出者走一般性錯誤。 */
const FAILURE_HANDLERS = {
  429: () => ({ gate: null, output: RUN_MESSAGES.LIMIT_REACHED, trialRunsRemaining: 0 }),
  503: () => ({
    gate: null,
    output: RUN_MESSAGES.SANDBOX_UNAVAILABLE,
    trialRunsRemaining: UNCHANGED,
  }),
  409: () => ({ gate: GateState.SUBMITTED, output: '', trialRunsRemaining: UNCHANGED }),
  410: () => ({ gate: GateState.EXPIRED, output: '', trialRunsRemaining: UNCHANGED }),
};

export function describeTermination(reason) {
  return TERMINATION_LABELS[reason] || (typeof reason === 'string' ? reason : '');
}

export function formatRunOutput(result) {
  const data = result || {};
  const parts = [data.stdout, data.stderr].filter((part) => part);
  return parts.length ? parts.join('\n') : RUN_MESSAGES.EMPTY_OUTPUT;
}

export function formatRunMeta(result) {
  const data = result || {};
  const parts = [describeTermination(data.termination_reason), `耗時 ${data.duration_ms ?? 0} ms`];
  if (data.truncated) parts.push(RUN_MESSAGES.TRUNCATED);
  return parts.filter(Boolean).join('｜');
}

export function afterTrialRun(remaining) {
  return Math.max((Number.isFinite(remaining) ? remaining : 0) - 1, 0);
}

export function canRun(remaining) {
  return Number.isFinite(remaining) && remaining > 0;
}

/**
 * 把試跑失敗轉換成三件事：要不要換畫面、輸出區顯示什麼、剩餘次數怎麼變。
 *
 * 訊息一律取自本地字串表，不回放後端原文（與 gate.js 同一理由，FR-134）。
 */
export function resolveRunFailure(error) {
  const status = error && typeof error.status === 'number' ? error.status : 0;
  const handler = FAILURE_HANDLERS[status];
  if (handler) return handler();
  return { gate: null, output: RUN_MESSAGES.FAILED, trialRunsRemaining: UNCHANGED };
}
