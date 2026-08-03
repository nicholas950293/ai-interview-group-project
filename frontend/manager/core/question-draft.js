// 把面試官打的一段文字轉成後端要的 Question（純函式，不碰 DOM）。
//
// 後端的 Question 至少需要 title、difficulty 與 description 三個欄位，
// 而畫面上只有一個輸入框。這裡的規則是「第一行是標題，其餘是敘述」——
// 這是整頁唯一有判斷的地方，因此抽出來讓 tests/question-draft.test.js 蓋住。

export const MAX_TITLE_LENGTH = 200;
export const DEFAULT_DIFFICULTY = 'MEDIUM';

export const DRAFT_ERRORS = {
  EMPTY: '請先輸入題目內容。',
};

/**
 * 兩欄皆空時回傳空陣列——非工程類職缺不需要測資，
 * 工程類的缺漏由後端擋下並回傳明確訊息（FR-026）。前端不自行補佔位測資：
 * 假測資會讓自動評測的正確性維度失去意義。
 */
function buildTestCases(stdin, expectedStdout) {
  const input = typeof stdin === 'string' ? stdin : '';
  const output = typeof expectedStdout === 'string' ? expectedStdout : '';
  if (!input.trim() && !output.trim()) return [];

  return [{ name: '範例', stdin: input, expected_stdout: output, is_hidden: false }];
}

/**
 * @returns {{ok: true, question: object} | {ok: false, error: string}}
 */
export function buildQuestion({ text, stdin, expectedStdout } = {}) {
  const body = typeof text === 'string' ? text.trim() : '';
  if (!body) return { ok: false, error: DRAFT_ERRORS.EMPTY };

  // body 已去除前後空白，因此第一行必定有內容——開頭的空行會被自動略過，
  // 面試官不需要為了「不要留空行」而分心。
  const lines = body.split('\n');
  const title = lines[0].trim().slice(0, MAX_TITLE_LENGTH);

  // 只有一行時，標題與敘述相同——後端要求 description 非空，
  // 而把唯一那行也當作敘述，比塞一個佔位字串誠實。
  const rest = lines.slice(1).join('\n').trim();

  // 刻意不填 source：面試官手打的題目既不是題庫題也不是 AI 生成，
  // 後端允許留空，硬塞一個值等於在題目快照裡謊報來源。
  // 也不填 language：應徵者作答頁本來就有語言選擇，由作答者自己決定。
  return {
    ok: true,
    question: {
      title,
      difficulty: DEFAULT_DIFFICULTY,
      description: rest || title,
      test_cases: buildTestCases(stdin, expectedStdout),
    },
  };
}
