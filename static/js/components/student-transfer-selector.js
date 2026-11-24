/* Common assignment/quiz/discussion/roster/resource student selection.
   더블클릭하면 바로 반대편으로(왼쪽=추가, 오른쪽=제외). 반을 고르면 그 반 학생을 대상에 자동으로 넣습니다(autoFill). */
(() => {
 'use strict';
 function init(root){
  if(root.dataset.initialized||!window.EduStudentBrowser)return;root.dataset.initialized='true';
  const field=root.querySelector('input[type=hidden]'),initial=document.getElementById(root.dataset.initialScriptId),status=root.querySelector('[data-selector-search-status]');
  const max=Number(root.dataset.maxCount)||200,selected=new Map(),marks=new Set(),removeMarks=new Set();let results=[],busy=false,failure=null;
  const norm=s=>({...s,student_id:String(s.student_id||s.student_no||''),name:s.name||s.student_name||'',selectable:s.selectable!==false && s.status!=='확인 필요'});
  try{JSON.parse(initial.textContent).map(norm).forEach(s=>selected.set(s.student_id,s));}catch(_){status.textContent='기존 선택을 불러오지 못했습니다. 저장하지 말고 다시 여세요.';root.closest('form')?.querySelectorAll('[type=submit]').forEach(b=>b.disabled=true);return;}
  const e=(tag,text,cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
  function sync(){field.value=Array.from(selected.keys()).join(',');field.dispatchEvent(new Event('change',{bubbles:true}));root.querySelector('[data-selector-selected-count]').textContent=selected.size;}
  function row(s,side){
   const already=side==='result'&&selected.has(s.student_id);
   const node=window.EduStudentBrowser.row(s,{checkbox:true,side,checkName:'selectorCheck',checked:(side==='result'?marks:removeMarks).has(s.student_id),
     disabled:side==='result'&&(already||!s.selectable||busy),badge:already?'추가됨':''});
   node.dataset.selectorSide=side;return node;
  }
  // '전체 선택' 체크칸: 조회된 학생(추가할 수 있는 줄)·선택된 학생을 한 번에 체크합니다. 일부만 체크되면 반쯤 찬 표시.
  const candidates=side=>side==='result'?results.filter(s=>s.selectable&&!selected.has(s.student_id)).map(s=>s.student_id):Array.from(selected.keys());
  function syncAll(){
   root.querySelectorAll('[data-selector-all]').forEach(box=>{const side=box.dataset.selectorAll,mark=side==='result'?marks:removeMarks,ids=candidates(side),n=ids.filter(id=>mark.has(id)).length;
    box.checked=Boolean(ids.length)&&n===ids.length;box.indeterminate=n>0&&n<ids.length;box.disabled=!ids.length;});
  }
  function buttons(){
   root.querySelector('[data-selector-add]').disabled=busy||!marks.size;root.querySelector('[data-selector-remove]').disabled=!removeMarks.size;
   root.querySelector('[data-selector-clear]').disabled=!selected.size;syncAll();
  }
  root.querySelectorAll('[data-selector-all]').forEach(box=>box.addEventListener('change',()=>{
   const side=box.dataset.selectorAll,mark=side==='result'?marks:removeMarks,ids=candidates(side);
   ids.forEach(id=>box.checked?mark.add(id):mark.delete(id));
   root.querySelectorAll(`[data-selector-check="${side}"]`).forEach(c=>{if(ids.includes(c.value))c.checked=box.checked;});
   buttons();
  }));
  function render(){
   const focused=document.activeElement?.matches('[data-selector-check]')?{id:document.activeElement.value,side:document.activeElement.dataset.selectorCheck}:null;
   const scrolls=Array.from(root.querySelectorAll('.student-transfer-list')).map(n=>n.scrollTop);
   const left=root.querySelector('[data-selector-results]'),right=root.querySelector('[data-selector-selected]');left.replaceChildren(...results.map(s=>row(s,'result')));right.replaceChildren(...Array.from(selected.values()).map(s=>row(s,'selected')));
   if(!results.length)left.append(failure?window.EduStudentBrowser.errorBox(failure.message,failure.retry):e('p','조건에 맞는 학생이 없습니다.','ux-hint'));
   if(!selected.size)right.append(e('p','선택한 학생이 여기에 표시됩니다.','ux-hint'));
   root.querySelector('[data-selector-result-count]').textContent=results.length+'명';
   buttons();sync();
   if(focused){const target=Array.from(root.querySelectorAll('[data-selector-check]')).find(n=>n.value===focused.id&&n.dataset.selectorCheck===focused.side);target?.focus({preventScroll:true});}
   root.querySelectorAll('.student-transfer-list').forEach((n,i)=>n.scrollTop=scrolls[i]||0);
  }
  function add(rows){
   const candidates=rows.map(norm).filter(s=>s.selectable&&!selected.has(s.student_id));
   if(selected.size+candidates.length>max){status.textContent=`최대 ${max}명입니다. 일부만 자동 추가하지 않았습니다. 선택 범위를 줄여 주세요.`;return;}
   candidates.forEach(s=>selected.set(s.student_id,s));marks.clear();render();status.textContent=`${candidates.length}명 추가 · 최종 ${selected.size}명. 등록 버튼을 누르면 저장됩니다.`;
  }
  const form=root.closest('form'),group=form?.querySelector('[name=group]');
  const browser=window.EduStudentBrowser.mount(root.querySelector('[data-student-browser]'),{getGroup:()=>group?.value||root.dataset.activityGroup||'',onResult:(rows,meta)=>{results=rows.map(norm);failure=meta?.error?meta:null;marks.clear();render();},onAll:add,onBusy:b=>{busy=b;render();}});
  // 체크만 바뀔 때는 목록을 다시 그리지 않습니다(다시 그리면 두 번 누르는 사이 줄이 바뀌어 더블클릭이 잡히지 않음).
  root.addEventListener('change',ev=>{const b=ev.target;if(!b.matches('[data-selector-check]'))return;const mark=b.dataset.selectorCheck==='result'?marks:removeMarks;b.checked?mark.add(b.value):mark.delete(b.value);buttons();});
  root.querySelector('[data-selector-add]').addEventListener('click',()=>add(results.filter(s=>marks.has(s.student_id))));
  root.querySelector('[data-selector-remove]').addEventListener('click',()=>{removeMarks.forEach(id=>selected.delete(id));removeMarks.clear();render();});
  root.querySelector('[data-selector-clear]').addEventListener('click',()=>{selected.clear();removeMarks.clear();render();});
  root.addEventListener('dblclick',ev=>{
   const node=ev.target.closest('[data-selector-side]'),id=node?.querySelector('[data-selector-check]')?.value;if(!id)return;ev.preventDefault();
   if(node.dataset.selectorSide==='result'){const s=results.find(r=>r.student_id===id);if(s)add([s]);}
   else if(selected.delete(id)){removeMarks.delete(id);render();status.textContent=`1명 제외 · 최종 ${selected.size}명.`;}
  });
  // 반을 고르면 그 반 명단(EduTrack 반 학생)을 대상에 넣습니다. 기존 선택은 지우지 않습니다.
  async function autoFill(){
   const gid=group?.value;if(!gid)return;
   const url=new URL(root.querySelector('[data-student-browser]').dataset.browseUrl,location.href);
   Object.entries({mode:'activity',activity_group:gid,source:'lms',filter_group:gid,all:'1'}).forEach(([k,v])=>url.searchParams.set(k,v));
   try{const response=await fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!response.ok)return;
    const rows=(await response.json()).results||[];if(!rows.length){status.textContent='이 반에는 아직 학생 명단이 없습니다. 아래에서 학생을 골라 주세요.';return;}
    const before=selected.size;add(rows);status.textContent=`반 학생 ${selected.size-before}명을 대상에 넣었습니다 · 최종 ${selected.size}명. 빼려면 오른쪽에서 더블클릭하세요.`;}
   catch(_){/* 자동 채우기는 편의 기능: 실패해도 직접 고를 수 있습니다. */}
  }
  group?.addEventListener('change',()=>{marks.clear();browser.reconfigure();autoFill();});
  form?.addEventListener('submit',sync);render();
 }
 document.querySelectorAll('[data-student-transfer-selector]').forEach(init);
})();
