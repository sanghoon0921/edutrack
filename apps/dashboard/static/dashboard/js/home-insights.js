/* 학생·학부모 홈 '한눈에 보기'(11/10): 홈이 먼저 뜬 뒤 시험·출석·과제 현황을 불러와 넣고,
   도넛이 0에서 값까지 차오르고 숫자가 올라가는 한 번의 등장 움직임을 줍니다(움직임 줄이기 설정이면 바로 값). */
(() => {
  'use strict';
  const box = document.querySelector('[data-home-insights]');
  if (!box) return;
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ease = t => 1 - Math.pow(2, -10 * t);

  function countUp(el) {
    const to = Number(el.dataset.countTo);
    if (!Number.isFinite(to) || calm) return;
    const start = performance.now(), length = 900;
    const step = now => {
      // 첫 프레임 시각(now)이 start보다 조금 앞설 수 있어 0 아래로 내려가지 않게 막습니다(음수 숫자 깜빡임 방지).
      const t = Math.max(0, Math.min(1, (now - start) / length));
      el.textContent = String(t >= 1 ? to : Math.round(to * ease(t)));  // 마지막은 정확한 값
      if (t < 1) requestAnimationFrame(step);
    };
    el.textContent = '0';
    requestAnimationFrame(step);
  }

  function reveal() {
    box.classList.add('is-loaded');
    requestAnimationFrame(() => requestAnimationFrame(() => {
      box.classList.add('is-ready');
      box.querySelectorAll('[data-count-to]').forEach(countUp);
    }));
  }

  async function load() {
    box.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(box.dataset.url, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'text/html' }, signal: AbortSignal.timeout(20000) });
      if (!response.ok || response.redirected) throw new Error('bad');
      box.innerHTML = await response.text();
      reveal();
    } catch (error) {
      box.innerHTML = '';
      const p = document.createElement('p');
      p.className = 'hi-note';
      p.textContent = '시험·출석·과제 현황을 불러오지 못했습니다. ';
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'home-text-button';
      again.textContent = '다시 불러오기';
      again.addEventListener('click', load);
      p.append(again);
      box.append(p);
    } finally {
      box.setAttribute('aria-busy', 'false');
    }
  }
  load();
})();
