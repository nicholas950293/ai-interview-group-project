// assessment.html 的 DOM 契約。
//
// 把全部 id 收在一處的用意是：改動標記時只需要對照這一份清單，
// 不必到各個模組裡搜尋 getElementById。其餘模組一律接收節點，不自行查找。

const el = (id) => document.getElementById(id);

export function collectElements() {
  return {
    // 版面骨架
    notice: el('notice'),
    workspace: el('workspace'),
    jobTitle: el('job-title'),
    expiresAt: el('expires-at'),
    trialRemaining: el('trial-remaining'),

    // 題目
    question: {
      title: el('question-title'),
      description: el('question-description'),
      constraints: el('question-constraints'),
      samples: el('sample-cases'),
    },

    // 作答與試跑
    answer: {
      languageField: el('language-field'),
      languageSelect: el('language-select'),
      runButton: el('btn-run'),
      submitButton: el('btn-submit'),
      codeHost: el('code-editor'),
      textAnswer: el('text-answer'),
      runPanel: el('run-panel'),
      runOutput: el('run-output'),
      runMeta: el('run-meta'),
      stdinField: el('stdin-field'),
      stdin: el('run-stdin'),
      submitDialog: el('submit-dialog'),
      trialRemaining: el('trial-remaining'),
    },

    submitError: el('submit-error'),

    // AI 助教
    chat: {
      log: el('chat-log'),
      form: el('chat-form'),
      input: el('chat-input'),
      error: el('chat-error'),
    },
  };
}
