/* 수업 관리 > Class 리스트: '배정 학생 N명 보기'를 누르면 그 수업의 인트라넷 배정 학생 명단을 줄 아래로 펼친다.
   명단은 공용 학생 목록 부품(students:selector-browse, 50명씩)과 같은 줄 모양으로 그리고, 이름을 누르면 학생 상세로 간다. */
(() => {
  'use strict';
  const table = document.querySelector('[data-class-roster-url]');
  const B = window.EduStudentBrowser;
  if (!table || !B) return;
  const browseUrl = table.dataset.classRosterUrl, detailUrl = table.dataset.studentDetailUrl;

  async function fetchPage(classId, page) {
    const url = new URL(browseUrl, location.href);
    url.search = new URLSearchParams({mode: 'activity', source: 'intranet', class_id: classId, page: String(page)});
    let response;
    try { response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}}); }
    catch (_) { throw new Error('서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도하세요.'); }
    const data = await response.json().catch(() => ({}));
    if (response.redirected) throw new Error('로그인이 만료되었습니다. 다시 로그인하세요.');
    if (!response.ok) throw new Error(data.message || '명단을 불러오지 못했습니다.');
    return data;
  }

  function open(button) {
    const row = button.closest('tr'), classId = button.dataset.classRoster;
    const holder = document.createElement('tr');
    holder.dataset.rosterRow = classId;
    const cell = document.createElement('td');
    cell.colSpan = row.children.length;
    const list = document.createElement('div');
    list.className = 'st-table catalog-roster';
    const status = document.createElement('p');
    status.className = 'catalog-roster-status';
    status.textContent = '명단을 불러오는 중…';
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'catalog-roster-more';
    more.textContent = '더 보기';
    more.hidden = true;
    cell.append(status, list, more);
    holder.append(cell);
    row.after(holder);

    let page = 0;
    async function load() {
      more.hidden = true;
      list.querySelector('.st-error')?.remove();
      try {
        const data = await fetchPage(classId, page + 1);
        page += 1;
        const rows = data.results || [];
        list.append(...rows.map(item => B.row(item, {href: detailUrl.replace('__ID__', encodeURIComponent(item.student_id))})));
        status.textContent = data.total ? `배정 학생 ${data.total}명` : '배정된 학생이 없습니다.';
        more.hidden = page >= (data.pages || 1);
      } catch (error) {
        status.textContent = '';
        list.append(B.errorBox(error.message, load));
      }
    }
    more.addEventListener('click', load);
    load();
  }

  table.addEventListener('click', event => {
    const button = event.target.closest('[data-class-roster]');
    if (!button) return;
    const shown = button.closest('tr').nextElementSibling;
    if (shown && shown.dataset.rosterRow === button.dataset.classRoster) {
      shown.remove();
      button.setAttribute('aria-expanded', 'false');
      return;
    }
    button.setAttribute('aria-expanded', 'true');
    open(button);
  });
})();
