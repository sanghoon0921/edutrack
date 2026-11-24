/* 퀴즈 문항 정답 편집기. window.EduQuizEditor.mount(상자, 설정) 로 문항 하나의 정답 설정 칸을 그립니다.
   - 퀴즈 등록 화면의 여러 문항: static/js/components/quiz-builder.js
   - 문항 하나만 고치는 화면: 아래 [data-quiz-editor-form] (config_json 에 담아 보냄)
   서버 검증·저장 형태: apps/learning/quiz_types.py (clean_config). 유형을 바꿔도 앞서 적은 값은 유형별로 기억합니다. */
(() => {
  'use strict';
  const BLANK = /`([^`\n]+)`/g;
  const blankRow = () => ({ text: '' });
  const defaults = {
    MCQ: () => ({ choices: [blankRow(), blankRow(), blankRow(), blankRow()] }),
    MULTI: () => ({ choices: [blankRow(), blankRow(), blankRow(), blankRow()] }),
    TF: () => ({}),
    FILL: () => ({ blanks: [], bank: [] }),
    ORDER: () => ({ items: [blankRow(), blankRow(), blankRow()] }),
    MATCH: () => ({ pairs: [{ left: '', right: '' }, { left: '', right: '' }, { left: '', right: '' }], distractors: [] }),
    CATEGORY: () => ({ categories: [{ name: '', items: [] }, { name: '', items: [] }], distractors: [] }),
    SHORT: () => ({}),
  };
  let mounted = 0;

  function h(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else if (key === 'checked' || key === 'value') node[key] = value;
      else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : value);
    }
    node.append(...children.filter(child => child != null));
    return node;
  }
  const icon = name => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'et-icon'); s.setAttribute('aria-hidden', 'true'); const u = document.createElementNS('http://www.w3.org/2000/svg', 'use'); u.setAttribute('href', `#i-${name}`); s.append(u); return s; };
  const lines = text => text.split('\n').map(t => t.trim()).filter(Boolean);

  function mount(box, { type, config, modes, getPrompt, onChange }) {
    const uid = `quiz-edit-${++mounted}`;  // 문항마다 라디오 이름이 겹치지 않게
    const states = {};
    let current = type;
    states[current] = config && Object.keys(config).length ? structuredClone(config) : (defaults[current] || (() => ({})))();
    const state = () => (states[current] ||= (defaults[current] || (() => ({})))());
    const save = () => onChange?.();
    const text = (value, label, onInput) => h('input', { type: 'text', value: value || '', 'aria-label': label, oninput: e => { onInput(e.target.value); save(); } });
    const removeBtn = (label, onClick) => h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': label, title: label, onclick: () => { onClick(); render(); } }, icon('x'));
    const addBtn = (label, onClick) => h('button', { type: 'button', class: 'quiz-icon-btn quiz-add-btn', onclick: () => { onClick(); render(); box.querySelector('.quiz-edit-rows > :last-child input')?.focus(); } }, icon('plus'), label);
    const area = (value, label, onInput, placeholder) => h('textarea', { rows: 3, 'aria-label': label, placeholder, oninput: e => { onInput(lines(e.target.value)); save(); } }, (value || []).join('\n'));

    function choiceEditor(kind) {
      const s = state();
      return [h('h3', {}, kind === 'radio' ? '보기 (정답 하나 표시)' : '보기 (정답 모두 표시)'),
        h('div', { class: 'quiz-edit-rows' }, ...s.choices.map((choice, i) => h('div', { class: 'quiz-edit-row' },
          h('label', { class: 'quiz-edit-mark' }, h('input', { type: kind, name: `${uid}-correct`, checked: !!choice.correct,
            onchange: e => { if (kind === 'radio') s.choices.forEach(c => { c.correct = false; }); choice.correct = e.target.checked; save(); } }), '정답'),
          text(choice.text, `${i + 1}번 보기`, v => { choice.text = v; }), removeBtn(`${i + 1}번 보기 삭제`, () => s.choices.splice(i, 1))))),
        addBtn('보기 추가', () => s.choices.push(blankRow()))];
    }
    const editors = {
      MCQ: () => choiceEditor('radio'),
      MULTI: () => choiceEditor('checkbox'),
      TF() {
        const s = state();
        return [h('h3', {}, '정답'), h('div', { class: 'quiz-tf-edit', role: 'radiogroup', 'aria-label': '참/거짓 정답' },
          ...[[true, '참 (True)'], [false, '거짓 (False)']].map(([value, label]) => h('label', {}, h('input', { type: 'radio', name: `${uid}-tf`, checked: s.answer === value, onchange: () => { s.answer = value; save(); } }), label)))];
      },
      FILL() {
        const s = state();
        const answers = [...(getPrompt().matchAll(BLANK))].map(m => m[1].split('|').map(a => a.trim()).filter(Boolean));
        while (s.blanks.length < answers.length) s.blanks.push({ mode: 'text', options: [] });
        if (!answers.length) return [h('p', { class: 'quiz-help' }, '문제 칸에 `정답`처럼 백틱으로 빈칸을 표시하면 여기에 빈칸별 설정이 나타납니다.')];
        const rows = answers.map((alts, i) => {
          const blank = s.blanks[i];
          const options = h('input', { type: 'text', value: (blank.options || []).join(', '), 'aria-label': `${i + 1}번 빈칸 다른 보기`, placeholder: '다른 보기를 쉼표로 구분', hidden: blank.mode !== 'dropdown',
            oninput: e => { blank.options = e.target.value.split(',').map(t => t.trim()).filter(Boolean); save(); } });
          // 방식을 바꾸면 다시 그립니다(드롭다운 보기 칸·단어 은행 오답 칸이 나타나거나 사라짐).
          const mode = h('select', { 'aria-label': `${i + 1}번 빈칸 응답 방식`, onchange: e => { blank.mode = e.target.value; render(); box.querySelectorAll('select')[i]?.focus(); } },
            ...Object.entries(modes).map(([value, label]) => h('option', { value, selected: blank.mode === value }, label)));
          return h('div', { class: 'quiz-edit-row is-blank' }, h('strong', {}, `빈칸 ${i + 1}`), h('span', { class: 'quiz-blank-answer' }, alts.join(' / ')), mode, options);
        });
        const hasBank = s.blanks.slice(0, answers.length).some(b => b.mode === 'bank');
        return [h('h3', {}, '빈칸별 응답 방식'), h('p', { class: 'quiz-help' }, '직접 입력은 대소문자를 구분하지 않습니다. 드롭다운은 정답과 다른 보기 중 고르고, 단어 은행은 모든 단어 은행 빈칸의 정답이 한곳에 모여 나옵니다.'),
          h('div', { class: 'quiz-edit-rows' }, ...rows),
          hasBank ? h('label', { class: 'workflow-field' }, h('span', {}, '단어 은행에 더할 오답 (한 줄에 하나)'), area(s.bank, '단어 은행 오답', v => { s.bank = v; })) : null];
      },
      ORDER() {
        const s = state();
        return [h('h3', {}, '올바른 순서 (위에서부터)'), h('p', { class: 'quiz-help' }, '학생에게는 항상 섞인 순서로 보입니다.'),
          h('div', { class: 'quiz-edit-rows' }, ...s.items.map((item, i) => h('div', { class: 'quiz-edit-row' }, h('span', { class: 'quiz-edit-index' }, `${i + 1}`),
            text(item.text, `${i + 1}번째 항목`, v => { item.text = v; }),
            h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': '위로', disabled: i === 0, onclick: () => { [s.items[i - 1], s.items[i]] = [s.items[i], s.items[i - 1]]; render(); } }, icon('chevron-up')),
            h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': '아래로', disabled: i === s.items.length - 1, onclick: () => { [s.items[i + 1], s.items[i]] = [s.items[i], s.items[i + 1]]; render(); } }, icon('chevron-down')),
            removeBtn(`${i + 1}번째 항목 삭제`, () => s.items.splice(i, 1))))),
          addBtn('항목 추가', () => s.items.push(blankRow()))];
      },
      MATCH() {
        const s = state();
        return [h('h3', {}, '짝 (왼쪽 → 오른쪽 정답)'),
          h('div', { class: 'quiz-edit-rows' }, ...s.pairs.map((pair, i) => h('div', { class: 'quiz-edit-row' },
            text(pair.left, `${i + 1}번 왼쪽`, v => { pair.left = v; }), h('span', { class: 'quiz-edit-arrow', 'aria-hidden': 'true' }, '→'),
            text(pair.right, `${i + 1}번 오른쪽 정답`, v => { pair.right = v; }), removeBtn(`${i + 1}번 짝 삭제`, () => s.pairs.splice(i, 1))))),
          addBtn('짝 추가', () => s.pairs.push({ left: '', right: '' })),
          h('label', { class: 'workflow-field' }, h('span', {}, '헷갈리게 할 오답 보기 (한 줄에 하나, 선택)'), area(s.distractors, '오답 보기', v => { s.distractors = v; }))];
      },
      CATEGORY() {
        const s = state();
        return [h('h3', {}, '범주와 항목'),
          h('div', { class: 'quiz-category-edit' }, ...s.categories.map((category, i) => h('div', { class: 'quiz-category-edit-card' },
            h('div', { class: 'quiz-edit-row' }, text(category.name, `${i + 1}번 범주 이름`, v => { category.name = v; }), removeBtn(`${i + 1}번 범주 삭제`, () => s.categories.splice(i, 1))),
            area(category.items, `${i + 1}번 범주 항목`, v => { category.items = v; }, '이 범주에 들어갈 항목 (한 줄에 하나)')))),
          addBtn('범주 추가', () => s.categories.push({ name: '', items: [] })),
          h('label', { class: 'workflow-field' }, h('span', {}, '어느 범주에도 속하지 않는 오답 항목 (한 줄에 하나, 선택)'), area(s.distractors, '오답 항목', v => { s.distractors = v; }))];
      },
      SHORT: () => [],
    };
    function render() {
      box.replaceChildren(...editors[current]?.() || []);
      box.hidden = current === 'SHORT';
      save();
    }
    let fillTimer = null;
    const editor = {
      get type() { return current; },
      setType(next) { current = next; render(); },
      // 빈칸 채우기는 문제 문장이 바뀌면 빈칸 목록을 다시 그립니다.
      promptChanged() { if (current !== 'FILL') return; clearTimeout(fillTimer); fillTimer = setTimeout(render, 250); },
      value() { return current === 'SHORT' ? {} : state(); },
    };
    render();
    return editor;
  }
  window.EduQuizEditor = { mount, h, icon };

  // 문항 하나만 고치는 화면
  const form = document.querySelector('[data-quiz-editor-form]');
  if (!form) return;
  const initial = JSON.parse(document.getElementById('quiz-editor-data').textContent);
  const field = form.querySelector('[data-quiz-config]');
  const prompt = form.querySelector('textarea[name=prompt]');
  let editor = null;
  const save = () => { if (editor) field.value = editor.type === 'SHORT' ? '' : JSON.stringify(editor.value()); };
  const hints = () => form.querySelectorAll('[data-quiz-hint]').forEach(node => { node.hidden = node.dataset.quizHint !== editor.type; });
  editor = mount(form.querySelector('[data-quiz-answer-editor]'), { type: initial.type, config: initial.config, modes: initial.modes, getPrompt: () => prompt?.value || '', onChange: save });
  hints(); save();
  form.querySelectorAll('.quiz-type-card input').forEach(input => input.addEventListener('change', () => { editor.setType(input.value); hints(); }));
  prompt?.addEventListener('input', () => editor.promptChanged());
  form.addEventListener('submit', save);
})();
