// 題目與範例測資的渲染（FR-116）。
//
// 全部以建立節點 + textContent 寫入，不做字串拼接。原先的寫法是把題目內容
// 插進樣板字串再靠自寫的 escapeHtml 防護——那條防線只要有人漏加一次就破，
// 而 textContent 本身就不會把內容當標記解析，沒有「漏加」這個失敗模式。

function cell(labelText, value) {
  const block = document.createElement('div');
  block.className = 'sample__cell';

  const label = document.createElement('div');
  label.className = 'sample__label';
  label.textContent = labelText;

  const body = document.createElement('pre');
  body.className = 'sample__value';
  body.textContent = value;

  block.append(label, body);
  return block;
}

function sampleCaseCard(sampleCase) {
  const card = document.createElement('div');
  card.className = 'sample';

  const name = document.createElement('div');
  name.className = 'sample__name';
  name.textContent = sampleCase.name;

  const grid = document.createElement('div');
  grid.className = 'sample__grid';
  grid.append(cell('輸入', sampleCase.stdin), cell('預期輸出', sampleCase.expectedStdout));

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
