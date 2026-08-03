// 載入／送出失敗的說明（純函式，不碰 DOM）。
//
// 這一頁是給內部使用者的，錯誤訊息越具體越好——面試官看到「請稍後再試」時
// 無法判斷該重試、該換網址，還是該換權杖（spec 003 FR-211）。
//
// 特別是 404：頁面能開但 API 404，幾乎只有一個原因——這頁被開在只提供靜態檔的
// 伺服器上（例如 `python3 -m http.server --directory frontend`），那裡沒有後端。
// 這個情況極容易發生，也極容易說清楚，不該被吞成一句通用訊息。

/** 非 ApiError（例如連線失敗）時使用的狀態碼。 */
export const NETWORK_ERROR = 0;

export const LOAD_ERRORS = {
  NETWORK: '連不上伺服器。請確認後端仍在執行，以及這一頁的網址與後端是同一個來源。',
  NOT_FOUND:
    '找不到後端 API（404）。這一頁多半被開在只提供靜態檔的伺服器上——'
    + '請改用有跑後端的網址（例如 uvicorn 啟動的那個埠），或把 /api 反向代理到後端。',
  UNAUTHORIZED: '權杖無效或已過期，請重新貼上。',
  FORBIDDEN: '這組權杖沒有主管權限，或不屬於任何部門。',
  SERVER: '伺服器內部錯誤，請查看後端日誌。',
};

export function isAuthFailure(status) {
  return status === 401 || status === 403;
}

/**
 * @param {number} status HTTP 狀態碼；連線失敗時傳 NETWORK_ERROR
 * @param {string} [message] 後端回傳的訊息
 * @returns {string} 可行動的說明
 */
export function describeLoadFailure(status, message) {
  if (status === NETWORK_ERROR) return LOAD_ERRORS.NETWORK;
  if (status === 404) return LOAD_ERRORS.NOT_FOUND;
  if (status === 401) return LOAD_ERRORS.UNAUTHORIZED;
  if (status === 403) return LOAD_ERRORS.FORBIDDEN;

  // 後端自己的訊息通常最準確（缺測資、狀態不符都是可行動的說明），優先採用
  const detail = typeof message === 'string' ? message.trim() : '';
  if (detail) return `${detail}（HTTP ${status}）`;

  if (status >= 500) return LOAD_ERRORS.SERVER;
  return `請求失敗（HTTP ${status}）。`;
}
