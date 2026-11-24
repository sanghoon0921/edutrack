/* 글 속 주소를 파란 링크로(11/10): 화면의 글(공지·게시물·과제 설명·피드백·토론·메신저·리포트카드)에서
   https://… · www.… 를 새 창 링크로 바꾸고, 입력칸에 주소를 쓰면 바로 아래에 눌러 볼 수 있는 링크를 보여 줍니다.
   입력칸·버튼·이미 링크인 글·코드는 건드리지 않습니다. 새로 그려지는 메시지도 따라 바꿉니다. */
(() => {
  'use strict';
  const FIND = /(?:https?:\/\/|www\.)[^\s<>"'ㄱ-ㆎ가-힣]+/gi;
  const TRAIL = /[.,;:!?'"…)\]}]+$/;

  function trim(url) {
    let cut = url;
    for (;;) {
      const m = cut.match(TRAIL);
      if (!m) break;
      let tail = m[0];
      // 괄호가 주소 안에서 짝이 맞으면 남깁니다: …/Foo_(bar)
      while (tail.endsWith(')') && (cut.split('(').length - 1) >= (cut.split(')').length - 1)) {
        tail = tail.slice(0, -1);
        if (!tail) break;
      }
      if (!tail) break;
      cut = cut.slice(0, cut.length - tail.length);
      if (!TRAIL.test(cut)) break;
    }
    return cut;
  }

  function split(text) {
    const parts = [];
    let last = 0;
    String(text).replace(FIND, (raw, offset) => {
      const url = trim(raw);
      if (url.length < 8 && !url.toLowerCase().startsWith('www.')) return raw;
      if (offset > last) parts.push({ text: text.slice(last, offset) });
      parts.push({ url, href: url.toLowerCase().startsWith('www.') ? `https://${url}` : url });
      last = offset + url.length;
      return raw;
    });
    if (last < text.length || !parts.length) parts.push({ text: text.slice(last) });
    return parts;
  }

  const SKIP = 'a, button, textarea, input, select, option, script, style, code, pre, svg, [contenteditable], [data-no-linkify]';

  function anchor(doc, part) {
    const a = doc.createElement('a');
    a.href = part.href;
    a.textContent = part.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.className = 'et-autolink';
    return a;
  }

  function apply(root) {
    if (!root || !root.ownerDocument && root.nodeType !== 9) return;
    const doc = root.ownerDocument || root;
    const walker = doc.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */, {
      acceptNode(node) {
        if (!node.nodeValue || node.nodeValue.indexOf('.') < 0) return 2;
        const el = node.parentElement;
        if (!el || el.closest(SKIP)) return 2;
        FIND.lastIndex = 0;
        return FIND.test(node.nodeValue) ? 1 : 2;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const parts = split(node.nodeValue);
      if (!parts.some(p => p.url)) return;
      const frag = doc.createDocumentFragment();
      parts.forEach(p => frag.appendChild(p.url ? anchor(doc, p) : doc.createTextNode(p.text)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  function peek(field) {
    const doc = field.ownerDocument;
    let box = field.nextElementSibling;
    if (!box || !box.classList.contains('et-linkpeek')) {
      box = doc.createElement('div');
      box.className = 'et-linkpeek';
      box.setAttribute('aria-label', '입력한 링크');
      field.insertAdjacentElement('afterend', box);
    }
    const urls = split(field.value || '').filter(p => p.url);
    box.replaceChildren(...urls.slice(0, 5).map(p => anchor(doc, p)));
    box.hidden = !urls.length;
  }

  function watchFields(root) {
    root.querySelectorAll('textarea, input[type=text], input[type=url], input:not([type])').forEach(field => {
      if (field.dataset.linkpeek === 'off' || field.closest('[data-no-linkify]')) return;
      if (/(^|\.)(password|q|search)$/.test(field.name || '')) return;
      if (field.value && /https?:\/\/|www\./i.test(field.value)) peek(field);
    });
  }

  function start() {
    const doc = window.document;
    const main = doc.querySelector('main') || doc.body;
    apply(main);
    const chat = doc.querySelector('[data-chat-widget]');
    if (chat) apply(chat);
    watchFields(doc);
    doc.addEventListener('input', event => {
      const field = event.target;
      if (!field.matches || !field.matches('textarea, input[type=text], input[type=url], input:not([type])')) return;
      if (field.dataset.linkpeek === 'off' || field.closest('[data-no-linkify]')) return;
      if (/(^|\.)(password|q|search)$/.test(field.name || '')) return;
      if (/https?:\/\/|www\./i.test(field.value) || field.nextElementSibling?.classList.contains('et-linkpeek')) peek(field);
    });
    // 메신저·더 보기처럼 나중에 그려지는 글: 새로 붙은 부분만 다시 봅니다(우리가 만든 링크는 건너뜀).
    const observer = new MutationObserver(records => {
      records.forEach(r => r.addedNodes.forEach(node => {
        if (node.nodeType === 1 && !node.closest(SKIP)) apply(node);
      }));
    });
    [main, chat].forEach(el => { if (el) observer.observe(el, { childList: true, subtree: true }); });
  }

  window.EduLinkify = { split, apply };
  if (window.document.readyState === 'loading') window.document.addEventListener('DOMContentLoaded', start);
  else start();
})();
