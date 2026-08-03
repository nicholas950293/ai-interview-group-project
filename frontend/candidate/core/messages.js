// 面向應徵者的全部字串（FR-108、FR-134）。
//
// 集中於此有兩個理由：一是措辭要一致——應徵者是外部使用者，前後不一的用語會被
// 讀成系統不可靠；二是「不得把 token 或後端原始錯誤寫進畫面」這條規則需要一個
// 可稽核的位置，散在各個 ui 模組裡就無從檢查（tests/messages.test.js 守護）。

// 鍵刻意寫成字面值而非自 gate.js 匯入 GateState：gate.js 需要本模組的字串，
// 若本模組反過來匯入 gate.js 就形成循環，而 ESM 的循環會讓先被載入的一方
// 在 TDZ 中讀到未初始化的 const。兩者的一致性改由 tests/messages.test.js 守護。

/** 各終端畫面狀態的提示文字。READY 刻意沒有——它顯示的是作答工作區。 */
export const NOTICE_MESSAGES = {
  LINK_INCOMPLETE: '連結不完整，請確認信件中的網址是否完整複製後再開啟一次。',
  NOT_FOUND: '找不到此測驗連結，請確認網址是否正確，或聯繫 HR 協助處理。',
  EXPIRED: '此測驗連結已逾期，題目內容不再開放。請聯繫 HR 申請重新產生連結。',
  PREPARING: '題目準備中，主管尚未完成出題。請稍後再開啟此連結。',
  SUBMITTED: '你已完成提交，本連結已轉為唯讀，不可重複作答或修改。',
  LOAD_FAILED: '載入失敗，請稍後重新整理頁面。若持續發生，請聯繫 HR。',
};

/** 試跑區的訊息。429 與 503 都必須明確告知「仍可提交」（FR-119、FR-120）。 */
export const RUN_MESSAGES = {
  RUNNING: '執行中…（若目前有其他人正在執行，會排隊等候）',
  EMPTY_OUTPUT: '（無輸出）',
  LIMIT_REACHED: '已達試跑次數上限，無法再試跑。你仍然可以提交作答。',
  SANDBOX_UNAVAILABLE: '程式碼執行環境目前不可用，無法試跑。你仍然可以提交作答。',
  FAILED: '執行失敗，請稍後再試。若持續發生，你仍然可以直接提交作答。',
  TRUNCATED: '輸出已截斷',
};

/** 助教區的訊息。任何一則都必須說明作答不受影響（FR-129）。 */
export const CHAT_MESSAGES = {
  PENDING: '思考中…',
  GUARDRAIL: '助教僅提供觀念引導，不提供可直接提交的完整解答。',
  UNAVAILABLE: 'AI 助教目前不可用。你仍然可以作答、試跑與提交。',
  FAILED: '助教回覆失敗，請稍後再試。你仍然可以作答、試跑與提交。',
};

/** 提交確認。提交是不可逆的單次動作，因此措辭必須直白（FR-123）。 */
export const SUBMIT_MESSAGES = {
  CONFIRM_TITLE: '確認提交作答',
  CONFIRM_BODY: '提交後將無法修改作答，也不能再次提交。確定要提交嗎？',
  CONFIRM_OK: '確定提交',
  CONFIRM_CANCEL: '返回作答',
  FAILED: '提交失敗，請稍後再試。你的作答內容仍保留在畫面上。',
};

/** 沙箱契約（contracts/sandbox-runner.md）的終止原因對應中文。 */
export const TERMINATION_LABELS = {
  COMPLETED: '執行完成',
  TIMEOUT: '執行逾時',
  MEMORY_LIMIT: '超過記憶體上限',
  PIDS_LIMIT: '超過程序數上限',
  OUTPUT_LIMIT: '超過輸出上限',
  COMPILE_ERROR: '編譯／語法錯誤',
  SANDBOX_UNAVAILABLE: '執行環境不可用',
};

export function submittedMessage(when) {
  return `你已於 ${when} 完成提交，本連結已轉為唯讀，不可重複作答或修改。`;
}

export function submitSuccessMessage(when) {
  return `已於 ${when} 成功提交，感謝你的作答。後續結果將由 HR 另行通知。`;
}

export function trialRemainingLabel(remaining) {
  return `剩餘試跑次數：${remaining}`;
}

export function expiresAtLabel(when) {
  return `連結到期：${when}`;
}
