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

// 深色主題以 EditorView.theme 就地定義，而非再拉一個 CDN 主題套件：
// 少一個外部相依，且色票能與 css/candidate.css 保持同一組值。
const THEME = {
  '&': { backgroundColor: '#191c21', color: '#e2ded7', height: '100%', fontSize: '13px' },
  '.cm-scroller': {
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
    lineHeight: '1.75',
  },
  '.cm-content': { padding: '16px 0', caretColor: '#d3a06a' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#d3a06a' },
  '.cm-gutters': { backgroundColor: '#191c21', color: '#5b626b', border: 'none' },
  '.cm-activeLine': { backgroundColor: '#1e2229' },
  '.cm-activeLineGutter': { backgroundColor: '#1e2229', color: '#9aa0a8' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': {
    backgroundColor: '#33404d',
  },
  '.cm-panels': { backgroundColor: '#23282f', color: '#c2beb6' },
  '.cm-searchMatch': { backgroundColor: '#4a3c2a', outline: '1px solid #6b5433' },
  '&.cm-focused': { outline: 'none' },
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
    fallback.className = 'answer-input';
    fallback.setAttribute('aria-label', '程式碼作答');
    fallback.spellcheck = false;
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
      editor = new EditorView({
        doc,
        extensions: [basicSetup, support(), EditorView.theme(THEME, { dark: true })],
        parent: host,
      });
      fallback = null;
    } catch {
      mountFallback(doc);
    }
  }

  return { mount, getValue };
}
