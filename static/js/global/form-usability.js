/* Local UI helpers: no external assets, no stored passwords/drafts, no automatic writes. */
(() => {
 'use strict';
 // 고르는 즉시 거르기(11/19): data-auto-submit 이 붙은 선택 칸은 바꾸면 바로 폼을 보냅니다(성적 분석·메시지 반 고르기 등).
 document.addEventListener('change',e=>{const t=e.target;if(t instanceof HTMLSelectElement&&t.matches('select[data-auto-submit]'))t.form?.requestSubmit();});
 const elem=(tag,text,cls='')=>{const e=document.createElement(tag);e.textContent=text;e.className=cls;return e;};
 // 날짜 칸 옆 빠른 날짜 단추는 없앴습니다(11/19). 날짜 칸을 누르면 date-picker.js 달력이 아래에 열립니다.
 // 공개 시간 예약: 끄면 공개 시작 칸을 비워 저장 즉시 공개, 켜면 칸을 보여 줍니다(templates/components/schedule_toggle.html).
 document.querySelectorAll('[data-schedule-toggle]').forEach(box=>{
  const wrap=box.closest('.ux-schedule')?.querySelector('[data-schedule-field]'),input=wrap?.querySelector('input');if(!wrap)return;
  box.addEventListener('change',()=>{wrap.hidden=!box.checked;if(!box.checked&&input){input.value='';input.dispatchEvent(new Event('change',{bubbles:true}));}else input?.focus();});
 });
 // Narrow screens use two clear steps instead of stacking both large form panels.
 let tabIndex=0;
 document.querySelectorAll('.ux-editor-columns').forEach(columns=>{
  const panes=Array.from(columns.children);if(panes.length!==2)return;
  const selectorFirst=panes[0].querySelector('[data-student-transfer-selector]');
  const selectorLast=panes[1].querySelector('[data-student-transfer-selector]');
  const labels=selectorFirst?['학생 명단','담당 강사']:selectorLast?['내용 작성','학생 선택']:['내용 작성','대상·첨부 설정'];
  const nav=elem('div','','ux-editor-tabs');nav.setAttribute('role','tablist');nav.setAttribute('aria-label','등록 단계');
  const mq=window.matchMedia('(max-width:1199px)');let active=Math.max(0,panes.findIndex(p=>p.querySelector('.errorlist,.field-error')));
  const id='ux-pane-'+(++tabIndex),buttons=[];
  function update(){
   nav.hidden=!mq.matches;
   panes.forEach((pane,i)=>{pane.hidden=mq.matches&&i!==active;buttons[i].setAttribute('aria-selected',String(i===active));buttons[i].tabIndex=i===active?0:-1;});
  }
  panes.forEach((pane,i)=>{pane.id=id+'-'+i;const b=elem('button',labels[i],'ux-btn');b.type='button';b.id=pane.id+'-tab';b.setAttribute('role','tab');b.setAttribute('aria-controls',pane.id);pane.setAttribute('aria-labelledby',b.id);
   b.addEventListener('click',()=>{active=i;update();});b.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();active=1-active;update();buttons[active].focus();}});buttons.push(b);nav.append(b);
  });columns.before(nav);mq.addEventListener('change',update);
  columns.addEventListener('invalid',e=>{const i=panes.findIndex(p=>p.contains(e.target));if(i>=0){active=i;update();}},true);update();
 });
 document.querySelectorAll('form[data-compact-form]').forEach(form=>{
  form.addEventListener('invalid',event=>{let node=event.target.parentElement;while(node&&node!==form){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement;}},true);
  form.addEventListener('submit',event=>{
   if(form.dataset.uiSubmitting==='true'){event.preventDefault();return;}
   if(!event.defaultPrevented){form.dataset.uiSubmitting='true';form.setAttribute('aria-busy','true');}
  });
  form.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!event.isComposing&&event.keyCode!==229){event.preventDefault();const submit=form.querySelector('button[type=submit].primary');if(submit)form.requestSubmit(submit);else form.requestSubmit();}});
 });
 window.addEventListener('pageshow',()=>document.querySelectorAll('form[data-ui-submitting]').forEach(f=>{delete f.dataset.uiSubmitting;f.removeAttribute('aria-busy');}));
})();
