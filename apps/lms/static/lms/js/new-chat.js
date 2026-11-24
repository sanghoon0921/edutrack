/* 새 대화: 대화할 사람 체크 목록 + 이름 검색. 고른 사람은 위에 칩으로 보이고 누르면 뺍니다.
   강사·관리자는 여러 명(두 명 이상이면 그룹 대화), 학생은 한 명만(data-single). 서버: apps/lms/message_views.new_conversation */
(() => {
  'use strict';
  const form = document.querySelector('[data-chat-picker]');
  if (!form) return;
  const single = form.dataset.single === 'true';
  const search = form.querySelector('[data-chat-search]'), count = form.querySelector('[data-chat-picked]');
  const chosen = form.querySelector('[data-chat-chosen]'), start = form.querySelector('[data-chat-start]'), noMatch = form.querySelector('[data-chat-no-match]');
  const picks = [...form.querySelectorAll('.chat-pick')], pickAll = form.querySelector('[data-chat-pick-all]');
  const box = pick => pick.querySelector('input');
  const visible = () => picks.filter(p => !p.hidden).map(box);
  function update() {
    const on = picks.filter(p => box(p).checked);
    count.textContent = `${on.length}명 선택`;
    chosen.replaceChildren(...on.map(p => {
      const chip = document.createElement('button');
      chip.type = 'button'; chip.className = 'chat-chip'; chip.textContent = `${p.querySelector('span').textContent} ×`;
      chip.setAttribute('aria-label', `${p.querySelector('span').textContent} 빼기`);
      chip.addEventListener('click', () => { box(p).checked = false; update(); });
      return chip;
    }));
    picks.forEach(p => p.classList.toggle('is-on', box(p).checked));
    // 인원 추가 화면은 버튼에 data-label(예: '추가하기')을 달아 그 이름에 고른 사람 수를 붙입니다(11/16).
    if (start.dataset.label) start.textContent = on.length ? `${start.dataset.label} (${on.length}명)` : start.dataset.label;
    else start.textContent = on.length > 1 ? `그룹 대화 시작 (${on.length + 1}명)` : '대화 시작';
    start.disabled = !on.length;
    // '전체 선택'은 지금 보이는(검색으로 걸러진) 사람 기준입니다.
    if (pickAll) { const shown = visible(), n = shown.filter(i => i.checked).length; pickAll.checked = Boolean(shown.length) && n === shown.length; pickAll.indeterminate = n > 0 && n < shown.length; }
  }
  form.addEventListener('change', event => {
    if (event.target === pickAll) { visible().forEach(i => { i.checked = pickAll.checked; }); update(); return; }
    if (single && event.target.checked) picks.forEach(p => { if (box(p) !== event.target) box(p).checked = false; });
    update();
  });
  search?.addEventListener('input', () => {
    const q = search.value.trim().toLocaleLowerCase();
    picks.forEach(p => { p.hidden = Boolean(q) && !p.dataset.search.includes(q); });
    if (noMatch) noMatch.hidden = !picks.length || picks.some(p => !p.hidden);
    update();
  });
  update();
  search?.focus();
})();
