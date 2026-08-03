// 登入後要去哪（純函式，不碰 DOM）。
//
// `next` 來自網址查詢字串，也就是**使用者可控的輸入**。若原樣拿去導向，
// 這一頁就會變成開放重新導向（open redirect）：攻擊者可以寄出
// /login.html?next=https://evil.example 的連結，受害者在真的登入頁登入後
// 被送到釣魚站。因此只接受同源的絕對路徑，其餘一律退回角色預設頁。

/** 各角色登入後的預設落點。 */
export const ROLE_HOME = {
  HR: '/index.html',
  MANAGER: '/manager/ask.html',
};

export const FALLBACK_HOME = '/index.html';

/**
 * 判斷 next 是否為安全的站內路徑。
 *
 * 拒絕：協定絕對網址（https://…）、協定相對網址（//evil）、反斜線變形（/\evil）、
 * 以及任何不以單一 / 起頭的相對路徑。
 */
export function isSafeNext(next) {
  if (typeof next !== 'string' || !next) return false;
  if (!next.startsWith('/')) return false;
  if (next.startsWith('//') || next.startsWith('/\\')) return false;
  // 控制字元與空白可被用來繞過前面的字首檢查
  if (/[\u0000-\u0020\u007f]/.test(next)) return false;
  return true;
}

export function resolveRedirect(next, role) {
  if (isSafeNext(next)) return next;
  return ROLE_HOME[role] || FALLBACK_HOME;
}
