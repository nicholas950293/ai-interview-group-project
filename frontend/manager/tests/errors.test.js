// 失敗說明必須可行動（spec 003 FR-211）。
//
// 這組測試源於一次真實事故：出題頁被開在只提供靜態檔的伺服器上，API 回 404，
// 而畫面只顯示「請稍後再試」——面試官完全無從判斷問題在哪。

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  describeLoadFailure,
  isAuthFailure,
  LOAD_ERRORS,
  NETWORK_ERROR,
} from '../core/errors.js';

test('404 指出這頁多半開在沒有後端的靜態伺服器上', () => {
  const message = describeLoadFailure(404);
  assert.equal(message, LOAD_ERRORS.NOT_FOUND);
  assert.match(message, /靜態檔|反向代理/);
});

test('連線失敗與 404 是不同的說明——一個是後端沒開，一個是網址不對', () => {
  assert.equal(describeLoadFailure(NETWORK_ERROR), LOAD_ERRORS.NETWORK);
  assert.notEqual(describeLoadFailure(NETWORK_ERROR), describeLoadFailure(404));
});

test('401 與 403 分開說明：一個換權杖，一個換帳號', () => {
  assert.equal(describeLoadFailure(401), LOAD_ERRORS.UNAUTHORIZED);
  assert.equal(describeLoadFailure(403), LOAD_ERRORS.FORBIDDEN);
});

test('其餘狀態優先採用後端自己的訊息，並附上狀態碼', () => {
  const message = describeLoadFailure(409, '工程類題目必須包含至少一組可執行的測試案例');
  assert.match(message, /測試案例/);
  assert.match(message, /409/);
});

test('後端沒給訊息時仍有可讀的說明，不出現 undefined', () => {
  for (const status of [500, 502, 418]) {
    const message = describeLoadFailure(status);
    assert.ok(message.trim().length > 0);
    assert.ok(!/undefined|\[object/.test(message));
  }
  assert.equal(describeLoadFailure(500), LOAD_ERRORS.SERVER);
});

test('空白訊息不會被當成有內容', () => {
  assert.equal(describeLoadFailure(500, '   '), LOAD_ERRORS.SERVER);
});

test('isAuthFailure 只認 401 與 403', () => {
  assert.equal(isAuthFailure(401), true);
  assert.equal(isAuthFailure(403), true);
  for (const status of [0, 404, 409, 500]) assert.equal(isAuthFailure(status), false);
});
