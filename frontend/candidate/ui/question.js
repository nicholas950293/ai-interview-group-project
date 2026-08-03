// 題目與範例測資的渲染（FR-116）。
//
// 全部以建立節點 + textContent 寫入，不做字串拼接。原先的寫法是把題目內容
// 插進樣板字串再靠自寫的 escapeHtml 防護——那條防線只要有人漏加一次就破，
// 而 textContent 本身就不會把內容當標記解析，沒有「漏加」這個失敗模式。

function labelled(labelText, value) {
  const block = document.createElement('div');

  const label = document.createElement('div');
  label.className = 'text-slate-500';
  label.textContent = labelText;

  const body = document.createElement('pre');
  body.className = 'whitespace-pre-wrap';
  body.textContent = value;

  block.append(label, body);
  return block;
}

function sampleCaseCard(sampleCase) {
  const card = document.createElement('div');
  card.className = 'rounded border border-slate-200 p-2';

  const name = document.createElement('div');
  name.className = 'font-medium';
  name.textContent = sampleCase.name;

  const grid = document.createElement('div');
  grid.className = 'mt-1 grid gap-1 sm:grid-cols-2 font-mono';
  grid.append(labelled('輸入', sampleCase.stdin), labelled('預期輸出', sampleCase.expectedStdout));

  card.append(name, grid);
  return card;
}

export function renderQuestion(elements, question) {
  const { title, description, constraints, samples } = elements;

  if (title) title.textContent = question.title;
  if (description) description.textContent = question.description;

  if (constraints) {
    constraints.textContent = question.constraints;
    constraints.hidden = !question.constraints;
  }

  if (samples) {
    samples.replaceChildren(...question.sampleCases.map(sampleCaseCard));
    samples.hidden = question.sampleCases.length === 0;
  }
}
