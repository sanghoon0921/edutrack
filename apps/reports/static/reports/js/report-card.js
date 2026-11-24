/* 리포트카드: 학생 이동, 저장 안 한 입력 경고, 입력칸 자동 높이, 새로 만들기에서 반 고르면 수업 목록 다시 읽기, 인쇄. */
(() => {
  'use strict';
  const grow = area => { area.style.height = 'auto'; area.style.height = `${area.scrollHeight + 2}px`; };
  document.querySelectorAll('textarea[data-autogrow]').forEach(area => { grow(area); area.addEventListener('input', () => grow(area)); });

  const editor = document.querySelector('[data-rc-editor]');
  let dirty = false;
  if (editor) {
    editor.addEventListener('input', () => { dirty = true; });
    editor.addEventListener('submit', () => { dirty = false; });
    window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  }
  document.querySelector('[data-rc-jump]')?.addEventListener('change', event => {
    if (dirty && !window.confirm('저장하지 않은 입력이 있습니다. 저장하지 않고 다른 학생으로 갈까요?')) return;
    dirty = false;
    window.location.href = event.target.value;
  });

  // 새 리포트카드: 반을 고르면 그 반의 수업·모의고사 목록을 다시 읽느라 화면을 새로 엽니다.
  // 먼저 고른 양식·수업 유형·기간·제목은 주소에 실어 보내 그대로 남깁니다(11/10).
  const KEEP_ON_GROUP_CHANGE = ['form', 'term', 'course_type', 'period_start', 'period_end', 'week_base'];
  const create = document.querySelector('[data-rc-new]');
  // 고르는 순서(운영팀 11/17): 양식 → Term → 반. 반 목록은 고른 양식(반 이름에 SAT·TOEFL 등)과 Term에 맞는 반만 보여 줍니다.
  // 그 Term에 양식 이름이 들어간 반이 하나도 없으면 그 Term의 반을 모두 보여 줍니다.
  const SEASONS = { SP: 'SPRING', SM: 'SUMMER', FW: 'FALL / WINTER', WT: 'WINTER' };
  const seasonHeading = code => {
    const m = /^(\d{2})(\d{2})?(SP|SM|FW|WT)$/.exec((code || '').trim().toUpperCase());
    if (m) return `20${m[1]}${m[2] ? `–20${m[2]}` : ''} ${SEASONS[m[3]]}`;
    // 11/20: 인트라넷 Term 이름(예: 2026 가을 정규)도 계절 낱말로
    const named = /^\s*(\d{4})\s*(봄|여름|가을|겨울)/.exec(code || '');
    const KO = { 봄: SEASONS.SP, 여름: SEASONS.SM, 가을: SEASONS.FW, 겨울: SEASONS.WT };
    return named ? `${named[1]} ${KO[named[2]]}` : (code || '시즌');
  };
  function syncNewForm() {
    if (!create) return;
    const form = create.querySelector('input[name=form]:checked')?.value || '';
    const term = create.querySelector('select[name=term]')?.value || '';
    const select = create.querySelector('[data-rc-group]');
    const hint = create.querySelector('[data-rc-group-hint]');
    if (select) {
      const options = [...select.options].filter(o => o.value);
      const inTerm = options.filter(o => !term || o.dataset.term === term);
      const matching = inTerm.filter(o => !form || o.dataset.forms.split(' ').includes(form));
      const shown = new Set(matching.length ? matching : inTerm);
      options.forEach(o => { o.hidden = !shown.has(o); o.disabled = !shown.has(o); });
      if (select.selectedOptions[0]?.disabled) select.value = '';
      if (hint) hint.textContent = !shown.size ? '고른 Term에 반이 없습니다. Term을 바꾸거나 반에 Term을 정해 주세요.'
        : (form && !matching.length ? '이 Term에 양식 이름이 들어간 반이 없어 그 Term의 반을 모두 보여 줍니다.' : '양식과 Term에 맞는 반만 보입니다. 반 명단의 학생마다 카드가 하나씩 만들어집니다.');
    }
    create.querySelectorAll('[data-rc-preview]').forEach(box => { box.hidden = box.dataset.rcPreview !== form; });
    const empty = create.querySelector('[data-rc-preview-empty]');
    if (empty) empty.hidden = Boolean(form);
    create.querySelectorAll('[data-rc-preview-season]').forEach(node => { node.textContent = seasonHeading(term); });
    create.querySelectorAll('[data-rc-only]').forEach(node => { node.hidden = Boolean(form) && node.dataset.rcOnly !== form; });
  }
  create?.addEventListener('change', event => { if (event.target.matches('input[name=form], select[name=term]')) syncNewForm(); });
  syncNewForm();
  create?.querySelector('select[name=group]')?.addEventListener('change', event => {
    const url = new URL(window.location.href);
    if (event.target.value) url.searchParams.set('group', event.target.value); else url.searchParams.delete('group');
    const data = new FormData(create);
    KEEP_ON_GROUP_CHANGE.forEach(key => {
      const value = data.get(key);
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    });
    window.location.href = url.toString();
  });

  // 편집 화면에서 주차 행 더하기·표 빼기·칸 지우기처럼 다른 단추로 저장하면 같은 카드로 돌아옵니다.
  // 그때 화면을 맨 위로 올리지 않고 보던 자리에 그대로 둡니다. 더한 행은 잠깐 표시하고 첫 칸에 커서를 둡니다.
  const SPOT = 'rc-editor-spot';
  if (editor) {
    editor.addEventListener('submit', event => {
      const button = event.submitter;
      if (!button || !button.hasAttribute('formaction')) return;
      try {
        sessionStorage.setItem(SPOT, JSON.stringify({ path: window.location.pathname, y: window.scrollY, at: Date.now(),
          added: button.classList.contains('rc-block-add') }));
      } catch (e) { /* 저장소를 못 쓰면 평소처럼 위에서 시작 */ }
    });
    let spot = null;
    try { spot = JSON.parse(sessionStorage.getItem(SPOT) || 'null'); sessionStorage.removeItem(SPOT); } catch (e) { spot = null; }
    if (spot && spot.path === window.location.pathname && Date.now() - spot.at < 60000) {
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      window.scrollTo({ top: spot.y, behavior: 'instant' });
      if (spot.added) {
        const rows = editor.querySelectorAll('.rc-junior-table tbody tr:not(.rc-block-add-row), .rc-blocks tbody tr:not(.rc-block-add-row)');
        const last = rows[rows.length - 1];
        if (last) {
          // 주니어 주차는 두 줄(수업 내용·코멘트)이 한 묶음입니다.
          const pair = !last.querySelector('.rc-week') && last.previousElementSibling ? [last.previousElementSibling, last] : [last];
          pair.forEach(r => r.classList.add('rc-row-new'));
          last.closest('tbody')?.querySelectorAll('tr.rc-row-new input, tr.rc-row-new textarea')[0]?.focus({ preventScroll: true });
        }
      }
    }
  }

  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  // 코멘트 칸 지우기처럼 되돌릴 수 없는 단추는 한 번 더 묻습니다.
  document.querySelectorAll('[data-rc-confirm]').forEach(button => button.addEventListener('click', event => {
    if (!window.confirm(button.dataset.rcConfirm)) event.preventDefault();
  }));

  // 목록 거르기(Term·반·발송): 고르면 바로 다시 거릅니다.
  document.querySelectorAll('.rc-filter select[data-auto-submit]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));

  // 묶음 화면의 작성 현황: 강사·TA가 저장하면 15초 안에 관리자 화면에 보입니다(운영팀 11/17 '실시간 저장 현황').
  const statusTable = document.querySelector('[data-rc-status]');
  if (statusTable) {
    const refresh = async () => {
      if (document.hidden) return;
      try {
        const response = await fetch(statusTable.dataset.rcStatus, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
        if (!response.ok) return;
        const data = await response.json();
        data.cards.forEach(card => {
          const cell = statusTable.querySelector(`[data-rc-status-cell="${card.id}"]`);
          if (!cell) return;
          const badge = document.createElement('span');
          badge.className = card.saved ? 'rc-state is-saved' : 'rc-state';
          badge.textContent = card.saved ? '저장' : '작성 전';
          cell.replaceChildren(badge, document.createTextNode(card.saved ? ` ${card.updated}${card.by ? ` · ${card.by}` : ''}` : ''));
        });
        const saved = document.querySelector('[data-rc-saved]');
        if (saved) saved.textContent = String(data.saved);
      } catch (error) { /* 다음 차례에 다시 읽습니다 */ }
    };
    window.setInterval(refresh, 15000);
  }

  if (document.body.hasAttribute('data-rc-print')) {
    document.querySelector('[data-rc-print-now]')?.addEventListener('click', () => window.print());
    if (new URLSearchParams(window.location.search).get('print') === '1') {
      const ready = document.fonts ? document.fonts.ready : Promise.resolve();
      ready.then(() => window.setTimeout(() => window.print(), 300));
    }
  }

  // SAT 모의고사 고르는 표(11/20): 시험 이름으로 줄 거르기. 체크한 줄은 거르지 않고 남깁니다.
  document.querySelectorAll('[data-rc-mock-filter]').forEach(box => {
    box.addEventListener('input', () => {
      const words = box.value.trim().toLowerCase();
      box.closest('.rc-mock-pick')?.querySelectorAll('[data-rc-mock-row]').forEach(row => {
        row.hidden = Boolean(words) && !row.dataset.rcMockRow.includes(words) && !row.querySelector('input:checked');
      });
    });
    // 거르기 칸에서 Enter 를 눌러도 양식이 제출되지 않게 합니다.
    box.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
  });
})();
