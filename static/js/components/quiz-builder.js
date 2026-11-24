/* 퀴즈 등록 화면의 문항 칸(아래 칸 전체 폭): 왼쪽 번호 목록에서 문항을 고르면 오른쪽에 그 문항만 펼쳐 편집합니다.
   퀴즈와 함께 한 번에 저장(questions_json). 카드 하나 = 유형 · 배점 · 문제 · 정답 설정(EduQuizEditor).
   유형마다 색이 있습니다(static/css/components/quiz.css [data-type]). 서버 검증: apps/learning/forms.py QuizForm.clean_questions_json */
(() => {
  'use strict';
  const root = document.querySelector('[data-quiz-builder]');
  if (!root || !window.EduQuizEditor) return;
  const { mount, h, icon } = window.EduQuizEditor;
  const data = JSON.parse(document.getElementById('quiz-builder-data').textContent);
  const form = root.closest('form'), field = form.querySelector('[data-quiz-questions]');
  const summary = document.querySelector('[data-quiz-builder-summary]'), navList = document.querySelector('[data-quiz-builder-nav] .quiz-nav-list');
  const labels = Object.fromEntries(data.types.map(t => [t.value, t.label]));
  const icons = Object.fromEntries(data.types.map(t => [t.value, t.icon]));
  const cards = [];
  let current = null;
  // 서버가 돌려준 "N번 문항: …" 오류는 그 번호 탭에 표시합니다.
  const errorNumbers = new Set([...document.querySelectorAll('.quiz-builder .quiz-editor-errors p')].map(p => Number((p.textContent.match(/^(\d+)번 문항/) || [])[1])).filter(Boolean));

  function sync() {
    field.value = JSON.stringify(cards.map(c => ({ id: c.id, type: c.type.value, prompt: c.prompt.value, points: Number(c.points.value) || 0,
      correct_text: c.short.value, config: c.editor.value() })));
    const total = cards.reduce((sum, c) => sum + (Number(c.points.value) || 0), 0);
    summary.textContent = cards.length ? `${cards.length}문항 · 총 ${total}점` : '아직 문항이 없습니다';
    cards.forEach((c, i) => {
      const type = c.type.value, text = c.prompt.value.replace(/`([^`]*)`/g, '[ $1 ]').trim();
      c.node.dataset.type = type; c.tab.dataset.type = type;
      c.number.textContent = `${i + 1}번`;
      c.tabNumber.textContent = String(i + 1);
      c.tabMeta.textContent = `${labels[type]} · ${Number(c.points.value) || 0}점`;
      c.tabText.textContent = text || '문제를 입력하세요';
      c.tab.classList.toggle('is-empty', !text);
      c.tab.classList.toggle('is-current', c === current);
      c.tab.setAttribute('aria-selected', String(c === current));
      c.tab.tabIndex = c === current ? 0 : -1;
      c.up.disabled = i === 0; c.down.disabled = i === cards.length - 1;
      c.typeIcon.replaceChildren(icon(icons[type]));
    });
  }
  function show(card, focus = false) {
    current = card;
    cards.forEach(c => { c.node.hidden = c !== card; });
    empty.hidden = cards.length > 0;
    sync();
    if (focus && card) card.prompt.focus({ preventScroll: true });
  }
  function place() {
    navList.replaceChildren(...cards.map(c => c.tab));
    root.replaceChildren(empty, ...cards.map(c => c.node));
    show(cards.includes(current) ? current : cards[0] || null);
  }
  function move(card, step) {
    const i = cards.indexOf(card), j = i + step;
    if (j < 0 || j >= cards.length) return;
    [cards[i], cards[j]] = [cards[j], cards[i]];
    place(); card.tab.focus();
  }
  function hints(card) {
    card.fillHint.hidden = card.type.value !== 'FILL';
    card.shortField.hidden = card.type.value !== 'SHORT';
  }
  function addCard(item = {}) {
    const card = { id: Number.isInteger(item.id) ? item.id : null };
    card.number = h('strong', { class: 'quiz-card-number' });
    card.typeIcon = h('span', { class: 'quiz-card-icon', 'aria-hidden': 'true' });
    card.type = h('select', { 'aria-label': '문항 유형', onchange: () => { card.editor.setType(card.type.value); hints(card); sync(); } },
      ...data.types.map(t => h('option', { value: t.value, selected: (item.type || 'MCQ') === t.value }, t.label)));
    card.points = h('input', { type: 'number', min: 1, max: 1000, value: item.points || 1, 'aria-label': '배점', oninput: sync });
    card.up = h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': '앞으로', title: '앞으로', onclick: () => move(card, -1) }, icon('chevron-up'));
    card.down = h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': '뒤로', title: '뒤로', onclick: () => move(card, 1) }, icon('chevron-down'));
    const remove = h('button', { type: 'button', class: 'quiz-icon-btn', 'aria-label': '이 문항 삭제', title: '이 문항 삭제', onclick: () => {
      if (card.id && !window.confirm('이 문항을 지울까요? 저장해야 반영됩니다.')) return;
      const i = cards.indexOf(card);
      cards.splice(i, 1); current = cards[Math.min(i, cards.length - 1)] || null; place();
    } }, icon('trash'));
    card.prompt = h('textarea', { rows: 2, placeholder: '문제를 입력하세요', 'aria-label': '문제', oninput: () => { card.editor.promptChanged(); sync(); } }, item.prompt || '');
    card.fillHint = h('small', { class: 'quiz-help' }, '빈칸이 될 정답을 `정답`처럼 백틱(`)으로 감싸세요. 정답이 여러 개면 `Paris|파리`처럼 | 로 나눕니다.');
    card.short = h('input', { type: 'text', value: item.correct_text || '', placeholder: '정답 (대소문자·앞뒤 공백 무시)', 'aria-label': '단답형 정답', oninput: sync });
    card.shortField = h('label', { class: 'quiz-card-short' }, h('span', {}, '정답'), card.short);
    const box = h('div', { class: 'quiz-answer-editor' });
    card.node = h('article', { class: 'quiz-card', role: 'tabpanel' },
      h('header', { class: 'quiz-card-head' }, card.typeIcon, card.number, card.type,
        h('label', { class: 'quiz-card-points' }, card.points, h('span', {}, '점')), h('span', { class: 'quiz-card-tools' }, card.up, card.down, remove)),
      card.prompt, card.fillHint, card.shortField, box);
    card.tabNumber = h('b', { class: 'quiz-nav-number' });
    card.tabMeta = h('span', { class: 'quiz-nav-meta' });
    card.tabText = h('span', { class: 'quiz-nav-text' });
    card.tab = h('button', { type: 'button', class: 'quiz-nav-item', role: 'tab', onclick: () => show(card, true),
      onkeydown: event => {
        const i = cards.indexOf(card), next = { ArrowDown: i + 1, ArrowUp: i - 1, ArrowRight: i + 1, ArrowLeft: i - 1 }[event.key];
        if (next === undefined || !cards[next]) return;
        event.preventDefault(); show(cards[next]); cards[next].tab.focus();
      } }, card.tabNumber, h('span', { class: 'quiz-nav-body' }, card.tabMeta, card.tabText));
    card.editor = mount(box, { type: card.type.value, config: item.config, modes: data.modes, getPrompt: () => card.prompt.value, onChange: () => { if (cards.includes(card)) sync(); } });
    hints(card);
    cards.push(card);
    if (errorNumbers.has(cards.length)) card.tab.classList.add('is-error');
    return card;
  }
  const empty = h('p', { class: 'ux-hint quiz-builder-empty' }, '왼쪽 \'+ 문항 추가\'로 문항을 만드세요. 문항은 나중에 추가해도 됩니다.');
  (data.items || []).forEach(item => addCard(item));
  current = cards.find((c, i) => errorNumbers.has(i + 1)) || cards[0] || null;
  place();
  document.querySelector('[data-quiz-builder-add]')?.addEventListener('click', () => {
    const last = cards[cards.length - 1];
    const card = addCard({ type: last ? last.type.value : 'MCQ', points: last ? Number(last.points.value) || 1 : 1 });
    current = card; place(); card.prompt.focus({ preventScroll: true }); card.tab.scrollIntoView({ block: 'nearest' });
  });
  form.addEventListener('submit', sync, true);
})();
