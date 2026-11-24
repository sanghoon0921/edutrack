// 공용 학생 목록 부품(static/js/global/student-browser.js)을 브라우저 없이 실행해 보는 시험 도구.
// 사용: node student_browser_harness.js <student-browser.js 경로> <사례 이름>  → 결과를 JSON 한 줄로 출력
// 실제 화면 대신 이 부품이 쓰는 기능만 흉내 낸 가짜 요소·가짜 시계·가짜 네트워크를 쓴다.
'use strict';
const fs = require('fs');
const vm = require('vm');

const [, , scriptPath, caseName] = process.argv;

// 가짜 시계: setTimeout 을 실제로 기다리지 않고 advance(ms) 로 시간을 앞당긴다.
function makeClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    setTimeout(fn, ms = 0) { const id = nextId++; timers.set(id, { at: now + ms, fn }); return id; },
    clearTimeout(id) { timers.delete(id); },
    advance(ms) {
      const end = now + ms;
      for (;;) {
        let next = null;
        for (const [id, timer] of timers) if (timer.at <= end && (!next || timer.at < next.at)) next = { id, ...timer };
        if (!next) break;
        timers.delete(next.id);
        now = next.at;
        next.fn();
      }
      now = end;
    },
  };
}

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.attributes = {};
    this.textContent = '';
    this.className = '';
    this.value = '';
    this.label = '';
    this.hidden = false;
    this.disabled = false;
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes.filter(Boolean); }
  remove() {}
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type, extra = {}) {
    const event = { type, target: this, key: '', keyCode: 0, isComposing: false, preventDefault() {}, ...extra };
    (this.listeners[type] || []).forEach(fn => fn(event));
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  get options() {
    const found = [];
    const walk = node => node.children.forEach(child => { if (child.tagName === 'OPTION') found.push(child); else walk(child); });
    walk(this);
    return found;
  }
  get text() { return [this.textContent, ...this.children.map(child => child.text)].filter(Boolean).join(' '); }
  find(predicate) {
    for (const child of this.children) {
      if (predicate(child)) return child;
      const inner = child.find(predicate);
      if (inner) return inner;
    }
    return null;
  }
}

const reply = (data, status = 200) => Promise.resolve({ ok: status < 400, status, redirected: false, json: async () => data });
const offline = () => Promise.reject(new TypeError('Failed to fetch'));
const flush = async () => { for (let i = 0; i < 20; i += 1) await new Promise(resolve => setImmediate(resolve)); };

// 스크립트를 새 가짜 창에 읽어 들인다. directories: 처음부터 화면에 있는 관리자 학생 검색 영역.
function load({ directories = [] } = {}) {
  const clock = makeClock();
  const requests = [];
  let respond = offline;
  const window = { addEventListener() {} };
  const document = {
    createElement: tag => new FakeElement(tag),
    querySelectorAll: selector => (selector === '[data-student-directory]' ? directories : []),
  };
  const fetch = (url, init = {}) => {
    requests.push(String(url));
    return new Promise((resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      Promise.resolve().then(() => respond(String(url), init)).then(resolve, reject);
    });
  };
  const context = vm.createContext({
    window, document, console, URL, AbortController, fetch,
    location: { href: 'http://edutrack.test/students/', origin: 'http://edutrack.test' },
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
  });
  vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), context, { filename: scriptPath });
  return { B: window.EduStudentBrowser, clock, requests, setNetwork(fn) { respond = fn; } };
}

// 거르기 막대(templates/components/student_filters.html)의 필요한 부분만 만든다.
function makeFilterBar() {
  const scope = new FakeElement('select');
  const everyone = new FakeElement('option');
  everyone.value = '';
  everyone.textContent = '전체';
  scope.append(everyone);
  const retry = new FakeElement('button');
  retry.hidden = true;
  const parts = {
    '[data-browse-scope]': scope,
    '[data-browse-q]': new FakeElement('input'),
    '[data-browse-status]': new FakeElement('p'),
    '[data-browse-retry]': retry,
  };
  const root = new FakeElement('div');
  root.dataset.browseUrl = '/students/selector/browse/';
  root.dataset.optionsUrl = '/students/selector/options/';
  root.querySelector = selector => parts[selector] || null;
  return { root, parts };
}

// '김지훈'을 칠 때 한글 입력기가 보내는 값. commit: 앞 글자가 끝나고 새 글자 조합이 시작된다.
const NAME = [
  { value: 'ㄱ' }, { value: '기' }, { value: '김' },
  { value: '김ㅈ', commit: true }, { value: '김지' }, { value: '김짛' },
  { value: '김지후', commit: true }, { value: '김지훈' },
];

// 한글 입력기처럼 이벤트를 보낸다. 조합 중인 글자도 값에 들어 있고,
// 마지막 글자는 다른 곳을 누르거나 Enter·Space 를 누르기 전까지 조합 중으로 남는다.
function typeKorean(input, clock, steps, gap = 80) {
  for (const step of steps) {
    if (step.commit && input.composing) { input.fire('compositionend'); input.composing = false; }
    if (!input.composing) { input.fire('compositionstart'); input.composing = true; }
    input.value = step.value;
    input.fire('input', { isComposing: true });
    clock.advance(gap);
  }
}

function liveSearch() {
  const { B, clock } = load();
  const input = new FakeElement('input');
  const runs = [];
  B.liveInput(input, () => runs.push(input.value));
  return { input, clock, runs };
}

const cases = {
  'korean-name-pause'() {
    const { input, clock, runs } = liveSearch();
    typeKorean(input, clock, NAME);
    clock.advance(1000);
    return runs;
  },
  'unfinished-letter-waits'() {
    const { input, clock, runs } = liveSearch();
    typeKorean(input, clock, NAME.slice(0, 1));
    clock.advance(1000);
    const afterJamo = runs.slice();
    typeKorean(input, clock, NAME.slice(1, 3));
    clock.advance(1000);
    return { afterJamo, runs };
  },
  'commit-after-pause-no-repeat'() {
    const { input, clock, runs } = liveSearch();
    typeKorean(input, clock, NAME);
    clock.advance(1000);
    input.fire('compositionend');
    input.composing = false;
    clock.advance(1000);
    return runs;
  },
  'enter-runs-at-once'() {
    const { input, clock, runs } = liveSearch();
    input.value = '7102';
    input.fire('input');
    input.fire('keydown', { key: 'Enter' });
    const atEnter = runs.slice();
    clock.advance(1000);
    return { atEnter, runs };
  },
  async 'failure-then-retry'() {
    const net = load();
    const { root, parts } = makeFilterBar();
    const seen = [];
    net.B.mount(root, { onResult: (rows, meta) => seen.push({ rows: rows.length, meta: meta || {} }) });
    await flush();
    const failed = seen[seen.length - 1];
    const result = {
      error: !!failed.meta.error,
      message: failed.meta.message || '',
      retry: typeof failed.meta.retry,
      barRetryShown: !parts['[data-browse-retry]'].hidden,
    };
    // 연결이 돌아온 뒤: 학생 목록이 수업·반 목록보다 먼저 도착하는 경우(실제 서버에서 흔함)
    net.setNetwork(url => (url.includes('/options/')
      ? new Promise(resolve => setImmediate(() => resolve(reply({ classes: [{ id: 7, name: 'SAT', status: 'P' }], groups: [], has_more: false }))))
      : reply({ results: [{ student_id: '6333', name: '김지훈' }], total: 1, pages: 1 })));
    if (typeof failed.meta.retry === 'function') failed.meta.retry();
    await flush();
    const last = seen[seen.length - 1];
    return {
      ...result,
      afterRows: last.rows,
      afterError: !!last.meta.error,
      options: parts['[data-browse-scope]'].options.map(option => option.value),
      barRetryShownAfter: !parts['[data-browse-retry]'].hidden,
      statusAfter: parts['[data-browse-status]'].textContent,
    };
  },
  async 'options-timeout'() {
    const net = load();
    net.setNetwork(url => (url.includes('/options/') ? new Promise(() => {}) : reply({ results: [], total: 0, pages: 1 })));
    const { root, parts } = makeFilterBar();
    net.B.mount(root, {});
    await flush();
    const shownBefore = !parts['[data-browse-retry]'].hidden;
    net.clock.advance(20000);
    await flush();
    return { shownBefore, shownAfter: !parts['[data-browse-retry]'].hidden, status: parts['[data-browse-status]'].textContent };
  },
  async 'directory-failure'() {
    const { root: bar, parts } = makeFilterBar();
    const list = new FakeElement('div');
    list.dataset.detailUrl = '/students/__ID__/';
    const head = new FakeElement('div');
    head.className = 'st-head';
    list.append(head);
    list.querySelector = selector => (selector === '.st-head' ? head : null);
    const directory = new FakeElement('section');
    directory.querySelector = selector => ({ '[data-remote-rows]': list, '[data-student-browser]': bar }[selector] || null);
    const net = load({ directories: [directory] });
    await flush();
    const q = parts['[data-browse-q]'];
    q.value = '김';
    q.fire('input');
    net.clock.advance(300);
    await flush();
    const shown = () => list.children.filter(child => child !== head);
    const failedText = shown().map(child => child.text).join(' | ');
    const retry = list.find(child => child.tagName === 'BUTTON' && child.textContent === '다시 시도');
    net.setNetwork(url => (url.includes('/options/')
      ? reply({ classes: [], groups: [], has_more: false })
      : reply({ results: [{ student_id: '6333', name: '김지훈' }], total: 1, pages: 1 })));
    if (retry) retry.fire('click');
    await flush();
    return { failedText, hasRetry: !!retry, afterRetry: shown().map(child => child.dataset.studentId || child.text) };
  },
};

(async () => {
  const run = cases[caseName];
  if (!run) { console.error(`unknown case: ${caseName}`); process.exit(2); }
  process.stdout.write(JSON.stringify(await run()));
})().catch(error => { console.error((error && error.stack) || String(error)); process.exit(1); });
