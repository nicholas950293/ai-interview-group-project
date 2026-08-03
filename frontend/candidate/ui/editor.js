// 程式碼編輯器（FR-112、FR-114、FR-115）。
//
// CodeMirror 自 CDN 動態載入。載入失敗時退回純文字輸入框——語法標示是體驗，
// 作答是能力，後者不得因為前者而中斷。切換語言時把現有內容帶到新實例，
// 應徵者不會因為改了語言就丟失已寫的程式碼。

const CODEMIRROR_CDN = 'https://esm.sh/codemirror@6.0.1';

const LANGUAGE_CDN = {
  javascript: 'https://esm.sh/@codemirror/lang-javascript@6.2.2',
  python: 'https://esm.sh/@codemirror/lang-python@6.1.6',
  go: 'https://esm.sh/@codemirror/lang-go@6.0.1',
  java: 'https://esm.sh/@codemirror/lang-java@6.0.1',
  cpp: 'https://esm.sh/@codemirror/lang-cpp@6.0.2',
};

export function createCodeEditor(host) {
  let editor = null; // CodeMirror 實例
  let fallback = null; // 退回的 textarea

  function getValue() {
    if (editor) return editor.state.doc.toString();
    if (fallback) return fallback.value;
    return '';
  }

  function mountFallback(doc) {
    editor = null;
    fallback = document.createElement('textarea');
    fallback.className = 'w-full p-4 font-mono text-sm min-h-[320px]';
    fallback.setAttribute('aria-label', '程式碼作答');
    fallback.value = doc;
    host.append(fallback);
  }

  async function mount(language) {
    const doc = getValue();
    host.replaceChildren();

    const languageUrl = LANGUAGE_CDN[language];
    try {
      const [{ EditorView, basicSetup }, languageModule] = await Promise.all([
        import(CODEMIRROR_CDN),
        import(languageUrl),
      ]);
      const support = Object.values(languageModule).find((value) => typeof value === 'function');
      editor = new EditorView({ doc, extensions: [basicSetup, support()], parent: host });
      fallback = null;
    } catch {
      mountFallback(doc);
    }
  }

  return { mount, getValue };
}
