/* 날짜 달력(11/19): 날짜·날짜시간 칸을 누르면 칸 바로 아래에 달력이 열립니다. 외부 라이브러리 없음.
   값은 원래 칸에 그대로 씁니다(날짜 YYYY-MM-DD, 날짜시간 YYYY-MM-DDTHH:MM) → 폼 보내는 방식은 바뀌지 않습니다.
   - 날짜 칸: 날짜를 누르면 고르고 닫힘. 날짜시간 칸: 날짜를 누르고 아래에서 시·분(10분 단위)을 고른 뒤 '완료'.
   - 키보드로 칸에 직접 입력·지우기도 그대로 됩니다. Esc·바깥 누르기로 닫힘. min·max 밖 날짜는 고를 수 없음. */
(() => {
 'use strict';
 const pad = n => String(n).padStart(2, '0');
 const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
 const MINUTES = [0, 10, 20, 30, 40, 50, 59];
 let panel = null, input = null, view = null;

 const ymd = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
 // '오늘'은 학원 시간대(서울) 기준: 해외 학생·강사 PC에서도 날짜가 어긋나지 않게
 const zone = document.body.dataset.uiTimezone || 'Asia/Seoul';
 function civilToday() {
  const v = {};
  new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date()).forEach(p => { v[p.type] = p.value; });
  return new Date(+v.year, +v.month - 1, +v.day);
 }
 const parseDate = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; };
 const parseTime = s => { const m = /T(\d{2}):(\d{2})/.exec(s || ''); return m ? { h: +m[1], m: +m[2] } : null; };
 const isDateTime = el => el.type === 'datetime-local';
 const defaultTime = el => /due|end|deadline|마감/i.test(el.name || '') ? { h: 23, m: 59 } : { h: 9, m: 0 };
 const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

 function emit(target) {
  target.dispatchEvent(new Event('input', { bubbles: true }));
  target.dispatchEvent(new Event('change', { bubbles: true }));
 }

 function currentTime() {
  return parseTime(input.value) || defaultTime(input);
 }

 function setValue(date, time) {
  if (!input) return;
  input.value = isDateTime(input) ? `${ymd(date)}T${pad(time.h)}:${pad(time.m)}` : ymd(date);
  emit(input);
 }

 function inRange(date) {
  const min = parseDate(input.min), max = parseDate(input.max);
  return !(min && date < min) && !(max && date > max);
 }

 function render() {
  panel.replaceChildren();
  const selected = parseDate(input.value), today = civilToday();
  const head = el('div', 'u-dp-head');
  const prev = el('button', 'u-dp-nav', '‹'), next = el('button', 'u-dp-nav', '›');
  prev.type = next.type = 'button';
  prev.setAttribute('aria-label', '이전 달'); next.setAttribute('aria-label', '다음 달');
  prev.addEventListener('click', () => { view = new Date(view.getFullYear(), view.getMonth() - 1, 1); render(); });
  next.addEventListener('click', () => { view = new Date(view.getFullYear(), view.getMonth() + 1, 1); render(); });
  const title = el('strong', 'u-dp-title', `${view.getFullYear()}년 ${view.getMonth() + 1}월`);
  title.setAttribute('aria-live', 'polite');
  head.append(prev, title, next);

  const grid = el('div', 'u-dp-grid');
  grid.setAttribute('role', 'grid');
  WEEK.forEach((w, i) => grid.append(el('span', 'u-dp-week' + (i === 0 ? ' is-sun' : ''), w)));
  const first = new Date(view.getFullYear(), view.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - first.getDay());
  for (let i = 0; i < 42; i++) {
   const day = new Date(start); day.setDate(start.getDate() + i);
   const b = el('button', 'u-dp-day', String(day.getDate()));
   b.type = 'button';
   b.setAttribute('aria-label', `${day.getFullYear()}년 ${day.getMonth() + 1}월 ${day.getDate()}일`);
   if (day.getMonth() !== view.getMonth()) b.classList.add('is-other');
   if (day.getDay() === 0) b.classList.add('is-sun');
   if (ymd(day) === ymd(today)) { b.classList.add('is-today'); b.setAttribute('aria-current', 'date'); }
   if (selected && ymd(day) === ymd(selected)) { b.classList.add('is-selected'); b.setAttribute('aria-pressed', 'true'); }
   if (!inRange(day)) { b.disabled = true; }
   b.addEventListener('click', () => {
    setValue(day, currentTime());
    if (isDateTime(input)) render(); else close(true);
   });
   grid.append(b);
  }
  panel.append(head, grid);

  if (isDateTime(input)) {
   const t = currentTime();
   const row = el('div', 'u-dp-time');
   const label = el('span', 'u-dp-time-label', '시간');
   const hour = el('select'), minute = el('select');
   hour.setAttribute('aria-label', '시'); minute.setAttribute('aria-label', '분');
   for (let h = 0; h < 24; h++) { const o = el('option', '', `${pad(h)}시`); o.value = h; o.selected = h === t.h; hour.append(o); }
   const mins = MINUTES.includes(t.m) ? MINUTES : [...MINUTES, t.m].sort((a, b) => a - b);
   mins.forEach(m => { const o = el('option', '', `${pad(m)}분`); o.value = m; o.selected = m === t.m; minute.append(o); });
   const apply = () => {
    const date = parseDate(input.value);
    if (date) setValue(date, { h: +hour.value, m: +minute.value });
   };
   hour.addEventListener('change', apply); minute.addEventListener('change', apply);
   row.append(label, hour, minute);
   panel.append(row);
  }

  const foot = el('div', 'u-dp-foot');
  const todayBtn = el('button', 'u-dp-link', '오늘'), clear = el('button', 'u-dp-link', '지우기'), done = el('button', 'u-dp-done', isDateTime(input) ? '완료' : '닫기');
  todayBtn.type = clear.type = done.type = 'button';
  todayBtn.addEventListener('click', () => {
   const d = civilToday();
   if (!inRange(d)) return;
   view = new Date(d.getFullYear(), d.getMonth(), 1);
   setValue(d, currentTime());
   if (isDateTime(input)) render(); else close(true);
  });
  clear.addEventListener('click', () => { input.value = ''; emit(input); render(); });
  done.addEventListener('click', () => close(true));
  foot.append(todayBtn, clear, done);
  panel.append(foot);
 }

 function place() {
  if (!panel || !input) return;
  const r = input.getBoundingClientRect();
  const width = panel.offsetWidth || 296, height = panel.offsetHeight || 360;
  let left = r.left + window.scrollX;
  left = Math.max(8 + window.scrollX, Math.min(left, window.scrollX + document.documentElement.clientWidth - width - 8));
  const below = r.bottom + 6, fitsBelow = below + height < window.innerHeight || r.top < height + 12;
  const top = fitsBelow ? below + window.scrollY : r.top + window.scrollY - height - 6;
  panel.style.left = `${left}px`;
  panel.style.top = `${top}px`;
 }

 function open(target) {
  if (target.disabled || target.readOnly) return;
  if (input === target && panel && !panel.hidden) return;
  input = target;
  const base = parseDate(input.value) || civilToday();
  view = new Date(base.getFullYear(), base.getMonth(), 1);
  if (!panel) {
   panel = el('div', 'u-datepicker');
   panel.setAttribute('role', 'dialog');
   panel.setAttribute('aria-label', '날짜 고르기');
   panel.addEventListener('mousedown', e => { if (!(e.target instanceof Element && e.target.closest('select'))) e.preventDefault(); }); // 칸의 포커스를 지키기(시·분 고르기는 그대로)
   // 달력 안에서 누른 것은 '바깥 누르기'로 치지 않습니다(날짜를 누르면 달력을 다시 그려 누른 단추가 떨어져 나가기 때문)
   panel.addEventListener('click', e => e.stopPropagation());
   document.body.append(panel);
  }
  panel.hidden = false;
  render();
  place();
  input.setAttribute('aria-expanded', 'true');
 }

 function close(refocus) {
  if (!panel || panel.hidden) return;
  panel.hidden = true;
  if (input) { input.setAttribute('aria-expanded', 'false'); if (refocus) input.focus({ preventScroll: true }); }
  input = null;
 }

 const SELECTOR = '#main-content input[type=date], #main-content input[type=datetime-local]';
 function prepare(root) {
  root.querySelectorAll(SELECTOR).forEach(target => {
   if (target.dataset.datePicker) return;
   target.dataset.datePicker = 'on';
   target.setAttribute('aria-haspopup', 'dialog');
   target.setAttribute('aria-expanded', 'false');
  });
 }
 prepare(document);

 document.addEventListener('click', e => {
  const target = e.target instanceof Element ? e.target.closest(SELECTOR) : null;
  if (target) { prepare(document); open(target); return; }
  if (panel && !panel.hidden && !panel.contains(e.target)) close(false);
 });
 document.addEventListener('focusin', e => {
  const target = e.target instanceof Element ? e.target.closest(SELECTOR) : null;
  if (target && (!input || input !== target)) open(target);
 });
 document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && panel && !panel.hidden) { e.preventDefault(); close(true); }
  if (e.key === 'Tab' && panel && !panel.hidden && input && e.target === input) close(false);
 });
 document.addEventListener('input', e => {
  if (panel && !panel.hidden && e.target === input) { const d = parseDate(input.value); if (d) view = new Date(d.getFullYear(), d.getMonth(), 1); render(); }
 });
 window.addEventListener('resize', () => close(false));
 window.addEventListener('scroll', place, { passive: true });
})();
