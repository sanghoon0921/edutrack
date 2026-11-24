(() => {
 'use strict';
 const target=document.querySelector('[data-home-schedule]');if(!target)return;
 const count=document.getElementById('home-class-count'),note=document.querySelector('[data-schedule-note]'),retry=document.querySelector('[data-schedule-retry]');
 let busy=false;
 function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;}
 async function load(){
  if(busy)return;busy=true;retry.disabled=true;target.setAttribute('aria-busy','true');
  try {
   const response=await fetch(target.dataset.url,{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'},signal:AbortSignal.timeout(20000)});
   if(!response.ok||response.redirected)throw new Error('수업 일정을 확인하지 못했습니다. ‘다시 확인’을 눌러 주세요.');
   const data=await response.json();target.replaceChildren();
   count.textContent=String(data.items.filter(r=>r.state!=='cancelled').length)+(data.partial?'+':'');
   if(!data.items.length)target.append(element('p','home-empty',data.linked?'오늘 등록된 수업 일정이 없습니다.':'학생 연결 후 오늘 수업을 확인할 수 있습니다.'));
   for(const row of data.items){
    const article=element('article',`home-session is-${row.state}`),main=element('div','home-session-main');
    main.append(element('strong','',row.title));
    if(row.teacher)main.append(element('p','',row.teacher));
    const actions=element('div','home-session-actions');actions.append(element('span','home-pill',row.label));
    if(row.zoom_url){
      const a=element('a','home-button primary','Zoom 입장 ↗');a.href=row.zoom_url;a.target='_blank';a.rel='noopener noreferrer';a.setAttribute('aria-label',`${row.title} Zoom 입장 (새 창)`);actions.append(a);
    }
    main.append(actions);article.append(element('time','home-session-time',row.time),main);target.append(article);
   }
   note.textContent=data.partial?'일부 일정만 표시합니다. 내 수업 전체에서 확인하세요.':data.zoom_warning?'일정은 확인했지만 수업별 Zoom 링크를 불러오지 못했습니다.':`${data.date} · ${data.timezone} 기준 · 수업 계획을 확인했습니다.`;
  }catch(error){target.replaceChildren(element('p','home-warning',error.message || '일정을 불러오지 못했습니다.'));count.textContent='—';note.textContent='연결 상태를 확인한 후 다시 시도해 주세요.';}
  finally{busy=false;retry.disabled=false;target.setAttribute('aria-busy','false');}
 }
 retry.addEventListener('click',load);load();
})();
