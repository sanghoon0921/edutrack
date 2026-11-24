(() => {
  'use strict';
  // 반 고르기 즉시 거르기는 공용 form-usability.js 가 맡습니다(11/19).
  const panel=document.querySelector('[data-message-summary]'),tools=window.EduTrackPolling;
  if(!panel || !tools)return;
  const list=panel.querySelector('[data-message-summary-list]'),status=panel.querySelector('[data-message-summary-status]');
  let signature='';
  // 검색어·반 조건을 목록 링크와 쪽 이동에도 이어 붙입니다.
  const filter=panel.dataset.filter||'',keep=filter?`?${filter}`:'';
  function update(data) {
    const fresh=JSON.stringify(data);if(fresh===signature)return;
    const focused=document.activeElement?.closest('[data-conversation-id]')?.dataset.conversationId;
    const old=new Map(Array.from(list.querySelectorAll('[data-conversation-id]')).map(e=>[e.dataset.conversationId,e]));
    const next=[];
    for(const item of data.items){
      const id=String(item.id);let row=old.get(id);old.delete(id);
      if(!row){
        row=document.createElement('a');row.className='home-message-row';row.dataset.conversationId=id;
        const main=document.createElement('div');main.className='home-message-main';
        main.append(document.createElement('strong'),document.createElement('p'),document.createElement('span'));
        main.lastChild.className='home-kicker';const badge=document.createElement('span');badge.className='home-pill';row.append(main,badge);
      }
      // Only same-origin server-generated conversation paths are installed as hrefs.
      const url=new URL(item.url,window.location.origin);if(url.origin!==window.location.origin)continue;
      row.href=url.pathname+keep;row.querySelector('strong').textContent=item.title;
      row.querySelector('p').textContent=item.preview;
      let kicker=row.querySelector('.home-kicker'); if(!kicker){kicker=document.createElement('span');kicker.className='home-kicker';row.querySelector('.home-message-main').append(kicker);}
      kicker.textContent=`${item.group} · ${item.time}`;
      let badge=row.querySelector('.home-pill');if(!badge){badge=document.createElement('span');badge.className='home-pill';row.append(badge);}row.classList.toggle('is-current',url.pathname===location.pathname);if(panel.closest('.ux-chat-shell'))badge.hidden=!item.unread;badge.textContent=item.unread?'안 읽음':'읽음';badge.classList.toggle('is-unread',Boolean(item.unread));
      next.push(row);
    }
    old.forEach(row=>row.remove());
    Array.from(list.children).filter(e=>!e.hasAttribute('data-conversation-id')).forEach(e=>e.remove());
    for(let i=0;i<next.length;i++) if(list.children[i]!==next[i])list.insertBefore(next[i],list.children[i] || null);
    if(!next.length){const p=document.createElement('p');p.className='home-empty';p.textContent=filter?'조건에 맞는 대화가 없습니다.':'참여 중인 대화가 없습니다.';list.append(p);}
    if(focused)list.querySelector(`[data-conversation-id="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
    document.querySelectorAll('[data-unread-count]').forEach(e=>{e.textContent=String(data.unread_count);});
    const pagination=panel.querySelector('[data-live-pagination]');
    if(pagination && data.pages){
      // 쪽 번호(11/19): 다른 목록과 같은 모양 — ‹ 이전 · 1~10 · 다음 › (10쪽을 넘으면 11~20)
      pagination.replaceChildren();
      const hrefOf=page=>(panel.dataset.listUrl||location.pathname)+`?page=${page}`+(filter?`&${filter}`:'');
      const nav=document.createElement('nav');nav.className='et-pager';nav.setAttribute('aria-label','대화 쪽 이동');
      function step(text,page,label){const el=document.createElement(page?'a':'span');el.className='et-pager-step'+(page?'':' is-disabled');el.textContent=text;if(page){el.href=hrefOf(page);el.setAttribute('aria-label',label);}else el.setAttribute('aria-disabled','true');nav.append(el);}
      step('‹ 이전',data.page>1?data.page-1:0,'이전 쪽');
      const nums=document.createElement('span');nums.className='et-pager-nums';
      const start=Math.floor((Math.max(1,data.page)-1)/10)*10+1,end=Math.min(data.pages,start+9);
      for(let n=start;n<=end;n++){const el=document.createElement(n===data.page?'span':'a');el.className='et-pager-num'+(n===data.page?' is-current':'');el.textContent=String(n);if(n===data.page)el.setAttribute('aria-current','page');else{el.href=hrefOf(n);el.setAttribute('aria-label',`${n}쪽`);}nums.append(el);}
      nav.append(nums);
      step('다음 ›',data.page<data.pages?data.page+1:0,'다음 쪽');
      if(data.pages>1)pagination.append(nav);
      // 처음 화면에 서버가 그린 쪽 번호는 실시간 쪽 번호로 대신합니다(두 줄로 겹치지 않게).
      panel.querySelectorAll(':scope > nav.et-pager').forEach(el=>{el.hidden=true;});
      panel.nextElementSibling?.classList.contains('lms-pagination') && (panel.nextElementSibling.hidden=true);
    }
    signature=fresh;
  }
  tools.start(async signal=>{const data=await tools.json(panel.dataset.url,{signal});if(signal.aborted||document.hidden)return;update(data);status.textContent=panel.closest('.ux-chat-shell')?'새 메시지 자동 확인 중':'5초 간격으로 새 메시지를 확인합니다.';},
    error=>{status.textContent=error.message;if(error.terminal){list.replaceChildren();document.querySelectorAll('[data-unread-count]').forEach(e=>e.textContent='—');}},false,{interval:panel.closest('.ux-chat-shell')?1000:5000});
})();
