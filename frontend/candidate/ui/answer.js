// 作答區：語言選擇、試跑、提交與提交前確認
// （FR-112、FR-113、FR-118、FR-122～FR-127）。
//
// 這個模組不做任何判定，也不呼叫 API：試跑結果怎麼呈現由 core/run-result.js 決定，
// 請求由呼叫端提供的 onRun／onSubmit 執行。它負責的是「畫面上有什麼、什麼時候能按」。

import { SUBMIT_MESSAGES, trialRemainingLabel } from '../core/messages.js';
import { canRun } from '../core/run-result.js';
import { createCodeEditor } from './editor.js';

/**
 * 提交前的明確確認（FR-123、FR-124）。
 *
 * 優先使用頁內 <dialog>；瀏覽器不支援時退回 window.confirm——確認步驟本身
 * 是不可省略的，能省的只有它長什麼樣子。
 */
function confirmSubmit(dialog) {
  if (!dialog || typeof dialog.showModal !== 'function') {
    return Promise.resolve(window.confirm(SUBMIT_MESSAGES.CONFIRM_BODY));
  }
  return new Promise((resolve) => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {
      once: true,
    });
    dialog.showModal();
  });
}

export function createAnswerPanel({ elements, view, onRun, onSubmit }) {
  const {
    languageField,
    languageSelect,
    runButton,
    submitButton,
    codeHost,
    textAnswer,
    runPanel,
    runOutput,
    runMeta,
    stdinField,
    stdin,
    submitDialog,
  } = elements;

  const editor = view.isEngineering ? createCodeEditor(codeHost) : null;
  let trialRunsRemaining = view.trialRunsRemaining;
  let busy = false;

  function hide(element) {
    if (!element) return;
    element.hidden = true;
    element.classList.add('hidden');
  }

  function show(element) {
    if (!element) return;
    element.hidden = false;
    element.classList.remove('hidden');
  }

  function getAnswer() {
    return view.isEngineering ? editor.getValue() : textAnswer.value;
  }

  function getLanguage() {
    // 非工程類提交時語言必須為空值（US3 情境 2）
    return view.isEngineering ? languageSelect.value : null;
  }

  function refreshControls() {
    runButton.disabled = busy || !canRun(trialRunsRemaining);
    // 提交永遠不因試跑次數而停用（FR-118、FR-119）
    submitButton.disabled = busy;
  }

  function setTrialRunsRemaining(remaining) {
    trialRunsRemaining = remaining;
    elements.trialRemaining.textContent = trialRemainingLabel(remaining);
    refreshControls();
  }

  function setBusy(value) {
    busy = value;
    refreshControls();
  }

  function showRunOutput(output, meta = '') {
    runOutput.textContent = output;
    runMeta.textContent = meta;
  }

  function setupEngineering() {
    languageSelect.value = view.language;
    languageSelect.addEventListener('change', () => editor.mount(languageSelect.value));
    editor.mount(view.language);
    bindRun();
  }

  function setupNonEngineering() {
    // 非工程類不得出現任何與程式碼執行有關的元素（FR-113）
    show(textAnswer);
    hide(codeHost);
    hide(languageField);
    hide(runButton);
    hide(runPanel);
    hide(stdinField);
    elements.trialRemaining.hidden = true;
  }

  function bindRun() {
    // 只有工程類才綁定：非工程類沒有編輯器，也不該存在試跑這個動作（FR-113）
    runButton.addEventListener('click', async () => {
      if (busy) return; // 進行中不重複送出（FR-122）
      setBusy(true);
      try {
        await onRun({
          code: editor.getValue(),
          language: languageSelect.value,
          stdin: stdin ? stdin.value : '',
        });
      } finally {
        setBusy(false);
      }
    });
  }

  submitButton.addEventListener('click', async () => {
    if (busy) return; // 進行中不重複送出（FR-127）
    if (!(await confirmSubmit(submitDialog))) return; // 取消不送出任何請求（FR-124）
    setBusy(true);
    try {
      await onSubmit({ answer: getAnswer(), language: getLanguage() });
    } finally {
      setBusy(false);
    }
  });

  if (view.isEngineering) setupEngineering();
  else setupNonEngineering();
  setTrialRunsRemaining(view.trialRunsRemaining);

  return { setTrialRunsRemaining, showRunOutput, getAnswer, getLanguage };
}
