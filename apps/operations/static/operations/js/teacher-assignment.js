/* 담당 학생 지정 (세 칸): ① 수업 찾기 → ② 학생(공용 부품) → ③ 현재 담당 학생.
   전체선택은 체크만 바꾸고, 저장은 옮기기(버튼·더블클릭·끌기·Enter)로만 한다. */
(() => {
 'use strict';
 const root=document.querySelector('[data-teacher-student-assignment]'),B=window.EduStudentBrowser;
 if(!root||!B||root.dataset.portalPickerReady)return;root.dataset.portalPickerReady='true';
 const $=s=>root.querySelector(s),$$=s=>Array.from(root.querySelectorAll(s));
 const LIMIT=100;
 const initial=id=>{try{return JSON.parse(document.getElementById(id).textContent)||[];}catch(_){return [];}};
 const idOf=s=>String(s.student_id||s.student_no||'');
 let assigned=initial('teacher-assignment-initial-data'),results=[],left=new Set(),right=new Set(),saving=false,drag=null;
 let classPage=1,classId='',classCtl=null,classSeq=0,searchFailure=null;
 const rowsById=new Map();  // 알고 있는 학생 줄 — 저장 응답에 이름만 와도 자세한 줄을 유지한다
 const remember=list=>list.forEach(s=>rowsById.set(idOf(s),s));
 remember(assigned);
 const status=$('[data-assignment-status]');
 const notify=(message,error=false)=>{status.textContent=message;status.classList.toggle('error',error);};
 const known=()=>new Set(assigned.map(idOf));
 const csrf=()=>root.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
 async function json(url,options={}){
   let response;
   try{response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,headers:{Accept:'application/json',...options.headers}});}
   catch(e){if(e.name==='AbortError')throw e;throw new Error('서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도하세요.');}
   if(response.redirected||[401,403].includes(response.status))throw new Error('로그인 또는 권한이 변경되었습니다. 화면을 새로 열어주세요.');
   const data=await response.json().catch(()=>({}));
   if(!response.ok||!data.ok)throw new Error(data.message||'조회·저장에 실패했습니다.');
   return data;
 }
 function paint(box,list,side,emptyText,failure=null){
   const ids=known(),chosen=side==='search'?left:right;
   box.replaceChildren(...list.map(s=>{
     const id=idOf(s),already=side==='search'&&ids.has(id);
     // 인트라넷에서 못 찾는 학생('확인 필요')도 오른쪽 칸에서는 제외할 수 있어야 하므로 왼쪽(②)에서만 잠근다.
     const node=B.row(s,{checkbox:true,side,checked:chosen.has(id),disabled:saving||already||(side==='search'&&s.selectable===false),badge:already?'담당 중':''});
     node.dataset.rowId=id;node.tabIndex=0;node.draggable=!already&&!saving;
     node.setAttribute('aria-label',`${s.name||id} — ${side==='search'?'더블클릭하면 담당 등록':'더블클릭하면 담당 제외'}`);
     return node;
   }));
   if(!list.length&&failure)box.append(B.errorBox(failure.message,failure.retry));  // 연결 실패는 '학생 없음'과 구분
   else if(!list.length){const p=document.createElement('p');p.className='portal-empty';p.textContent=emptyText;box.append(p);}
 }
 function selection(){
   $('[data-search-selection]').textContent=`${left.size}명 선택`;$('[data-assigned-selection]').textContent=`${right.size}명 선택`;
   $$('[data-transfer]').forEach(b=>{b.disabled=saving||(b.dataset.transfer==='add'?left.size:right.size)===0;});
 }
 function render(){
   const ids=known();
   left=new Set([...left].filter(n=>!ids.has(n)&&results.some(s=>idOf(s)===n)));
   right=new Set([...right].filter(n=>ids.has(n)));
   const typed=$('[data-browse-q]').value.trim();
   paint($('[data-search-list]'),results,'search',typed?'조건에 맞는 학생이 없습니다.':(classId?'이 수업 명단에 학생이 없습니다.':'수업을 고르거나 이름·학생번호를 입력하세요.'),searchFailure);
   paint($('[data-assigned-list]'),assigned,'assigned','등록된 담당 학생이 없습니다.');
   B.filterRows($('[data-assigned-list]'),{q:$('[data-assigned-q]').value});
   $('[data-result-count]').textContent=`${results.length}명`;$('[data-assigned-count]').textContent=`${assigned.length}명`;
   selection();
 }
 const browser=B.mount($('[data-student-browser]'),{mode:'teacher',requireInput:true,idleMessage:'수업을 고르거나 이름·학생번호를 입력하세요.',
   onResult:(rows,meta)=>{results=rows;searchFailure=meta?.error?meta:null;remember(rows);left.clear();render();},onBusy:busy=>root.classList.toggle('is-loading',busy)});

 // ① 수업 찾기
 async function classSearch(page=1){
   classCtl?.abort();classCtl=new AbortController();const ctl=classCtl,seq=++classSeq;classPage=page;
   const params=new URLSearchParams(new FormData($('[data-class-form]')));params.set('page',String(page));
   const box=$('[data-class-results]');
   const timeout=setTimeout(()=>ctl.abort(),20000);
   try{
     const data=await json(`${root.dataset.classUrl}?${params}`,{signal:ctl.signal});
     if(seq!==classSeq)return;
     if(page===1)box.replaceChildren();else box.querySelector('.st-error')?.remove();
     for(const item of data.classes){
       const b=document.createElement('button');b.type='button';b.className='portal-class-row';b.dataset.classId=String(item.id);b.dataset.classTitle=item.title;
       b.setAttribute('aria-pressed',String(classId===String(item.id)));
       const title=document.createElement('strong'),meta=document.createElement('small');title.textContent=item.title;
       meta.textContent=[item.term,item.status,`${item.student_count||0}명`].filter(Boolean).join(' · ');b.append(title,meta);box.append(b);
     }
     if(page===1&&!data.classes.length){const p=document.createElement('p');p.className='portal-empty';p.textContent='조건에 맞는 수업이 없습니다.';box.append(p);}
     $('[data-class-total]').textContent=`${data.total}개`;$('[data-class-more]').hidden=!data.has_more;
   }catch(e){
     if(seq!==classSeq)return;
     // 연결 실패·20초 초과: '수업 없음'과 구분해 그 자리에 안내하고, 같은 쪽을 다시 불러온다
     if(page===1)box.replaceChildren();else box.querySelector('.st-error')?.remove();
     box.append(B.errorBox(e.name==='AbortError'?'조회 시간이 초과되었습니다. 다시 조회하세요.':e.message,()=>classSearch(page)));
     $('[data-class-more]').hidden=true;
   }finally{clearTimeout(timeout);}
 }
 function pickClass(id,title){
   classId=id||'';left.clear();
   $$('[data-class-id]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.classId===classId)));
   $('[data-result-title]').textContent=classId?`② ${title} 명단`:'② 인트라넷 전체 학생';
   $('[data-class-clear]').hidden=!classId;
   browser.setScope(classId?{source:'intranet',class_id:classId}:{source:'all'});
 }
 const form=$('[data-class-form]');
 form.addEventListener('submit',e=>{e.preventDefault();classSearch(1);});
 B.liveInput(form.querySelector('[name=q]'),()=>classSearch(1));
 form.querySelectorAll('select').forEach(s=>s.addEventListener('change',()=>classSearch(1)));
 $('[data-class-more]').addEventListener('click',()=>classSearch(classPage+1));
 $('[data-class-results]').addEventListener('click',e=>{const b=e.target.closest('[data-class-id]');if(b)pickClass(b.dataset.classId===classId?'':b.dataset.classId,b.dataset.classTitle);});
 $('[data-class-clear]').addEventListener('click',()=>pickClass('',''));
 B.liveInput($('[data-assigned-q]'),()=>{right.clear();render();},120);

 // 옮기기
 async function move(action,numbers){
   if(saving)return;const ids=known();numbers=[...new Set(numbers)].filter(n=>action==='add'?!ids.has(n):ids.has(n));
   if(!numbers.length)return;if(numbers.length>LIMIT){notify(`한 번에 최대 ${LIMIT}명입니다. 선택을 줄여 주세요.`,true);return;}
   saving=true;render();notify(action==='add'?'담당 학생 등록 중…':'담당 학생 제외 중…');
   try{
     const data=await json(root.dataset.updateUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({action,student_nos:numbers})});
     assigned=(data.assigned||[]).map(a=>rowsById.get(String(a.student_no))||{student_id:String(a.student_no),name:a.student_name});
     left.clear();right.clear();notify(data.message);
   }catch(e){notify(e.message+' 현재 목록은 성공 확인 전까지 변경하지 않습니다.',true);}
   finally{saving=false;render();}
 }
 root.addEventListener('change',e=>{const node=e.target.closest('[data-row-id]');if(!node||e.target.type!=='checkbox')return;const set=node.dataset.side==='search'?left:right;e.target.checked?set.add(node.dataset.rowId):set.delete(node.dataset.rowId);selection();});
 root.addEventListener('click',e=>{
   const all=e.target.closest('[data-select-all]'),clear=e.target.closest('[data-clear-all]'),transfer=e.target.closest('[data-transfer]');
   if(all){
     if(all.dataset.selectAll==='search')left=new Set(results.map(idOf).filter(n=>!known().has(n)));
     else right=new Set($$('[data-assigned-list] [data-row-id]:not([hidden])').map(n=>n.dataset.rowId));
     render();notify('전체선택 완료. 아직 등록·제외하지 않았습니다.');
   }
   if(clear){clear.dataset.clearAll==='search'?left.clear():right.clear();render();}
   if(transfer)move(transfer.dataset.transfer,[...(transfer.dataset.transfer==='add'?left:right)]);
 });
 root.addEventListener('dblclick',e=>{const node=e.target.closest('[data-row-id]');if(!node||e.target.closest('input,button,a'))return;e.preventDefault();move(node.dataset.side==='search'?'add':'remove',[node.dataset.rowId]);});
 root.addEventListener('keydown',e=>{const node=e.target.closest('[data-row-id]');if(e.key==='Enter'&&node&&e.target===node){e.preventDefault();move(node.dataset.side==='search'?'add':'remove',[node.dataset.rowId]);}});
 root.addEventListener('dragstart',e=>{const node=e.target.closest('[data-row-id]');if(!node||saving)return;const set=node.dataset.side==='search'?left:right;const ids=set.has(node.dataset.rowId)?[...set]:[node.dataset.rowId];drag={action:node.dataset.side==='search'?'add':'remove',ids};e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain','edutrack-students');});
 $$('[data-drop-target]').forEach(zone=>{
   zone.addEventListener('dragover',e=>{if(drag&&drag.action===zone.dataset.dropTarget){e.preventDefault();e.dataTransfer.dropEffect='move';zone.classList.add('dragover');}});
   zone.addEventListener('dragleave',e=>{if(!zone.contains(e.relatedTarget))zone.classList.remove('dragover');});
   zone.addEventListener('drop',e=>{zone.classList.remove('dragover');if(drag&&drag.action===zone.dataset.dropTarget){e.preventDefault();const current=drag;drag=null;move(current.action,current.ids);}});
 });
 root.addEventListener('dragend',()=>{drag=null;$$('[data-drop-target]').forEach(z=>z.classList.remove('dragover'));});
 classSearch(1);render();
})();
