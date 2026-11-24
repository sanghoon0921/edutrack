/* Shared visible-tab poller. One in-flight request, no window reload, no hidden-tab traffic. */
(() => {
  'use strict';
  if (window.EduTrackPolling) return;
  // 11/10: 모든 화면의 배경 확인(안 읽은 수 등)은 15초. 대화창을 열어 둔 동안만 따로 빠르게(3초·대화 화면 2초).
  const INTERVAL = 15000;
  function start(task, onError = () => {}, immediate = true, options = {}) {
    const interval = Math.max(1000, Number(options.interval) || INTERVAL);
    let timer = null, controller = null, disposed = false, suspended = false, terminal = false, failures = 0;
    const available = () => !disposed && !suspended && !terminal && !document.hidden && navigator.onLine !== false;
    const schedule = (delay) => {
      clearTimeout(timer); timer = null;
      if (available()) timer = setTimeout(tick, delay);
    };
    async function tick() {
      timer = null;
      if (!available() || controller) return;
      controller = new AbortController();
      const mine = controller;
      const timeout = setTimeout(() => mine.abort('timeout'), 12000);
      let next = interval;
      try {
        const value = await task(mine.signal);
        if (mine.signal.aborted) return;
        failures = 0;
        if (value && value.catchUp) next = 250;
      } catch (error) {
        if (!available() || (mine.signal.aborted && mine.signal.reason !== 'timeout')) return;
        failures += 1;
        terminal = Boolean(error.terminal);
        next = Math.min(30000, interval * 2 ** Math.min(failures, 3));
        onError(error, terminal);
      } finally {
        clearTimeout(timeout); controller = null;
        if (!disposed) schedule(next);
      }
    }
    function wake() {
      clearTimeout(timer); timer = null;
      if (!available()) controller?.abort('paused');
      else if (!controller) tick();
    }
    function stop() { terminal = true; clearTimeout(timer); controller?.abort('stopped'); }
    function dispose() {
      disposed = true; stop();
      document.removeEventListener('visibilitychange', wake);
      window.removeEventListener('online', wake); window.removeEventListener('offline', wake);
    }
    document.addEventListener('visibilitychange', wake);
    window.addEventListener('online', wake); window.addEventListener('offline', wake);
    window.addEventListener('pagehide', event => {
      if (!event.persisted) {dispose(); return;}
      suspended=true; clearTimeout(timer); controller?.abort('paused');
    });
    window.addEventListener('pageshow', event => {if(event.persisted){suspended=false;wake();}});
    if (immediate) wake(); else schedule(interval);
    return {refresh:wake, stop, dispose};
  }
  async function json(url, options = {}) {
    const response = await fetch(url, {credentials:'same-origin',cache:'no-store',...options,
      headers:{Accept:'application/json',...(options.headers || {})}});
    const denied = response.redirected || [401,403,404].includes(response.status);
    if (denied) {
      const error = new Error('로그인 또는 대화 권한이 변경되었습니다. 다시 접속해 주세요.');
      error.terminal = true; throw error;
    }
    if (!response.ok) throw new Error('연결이 지연되고 있습니다. 입력 내용은 유지되며 자동으로 다시 확인합니다.');
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('응답을 확인하지 못했습니다. 연결 상태를 확인해 주세요.');
    return response.json();
  }
  window.EduTrackPolling = {start, json, interval:INTERVAL};
})();
