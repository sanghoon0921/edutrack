/* 공용 학생 목록 부품. 거르기를 바꿔도 저장된 선택은 바뀌지 않는다.
   mount: 서버(students:selector-browse)에서 학생을 불러오는 원격 방식
   row:   학생 한 줄 행 (templates/components/student_row.html 과 같은 구조)
   filterRows/mountLocal: 미리 그린 행을 브라우저에서 바로 거르는 로컬 방식 (담당 학생 화면) */
(() => {
  'use strict';
  if(window.EduStudentBrowser)return;
  const STATUS={P:'진행',W:'예정',E:'종료',C:'폐강'};
  const OFFLINE='서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도하세요.';
  const OPTIONS_FAILED='수업·반 목록을 불러오지 못했습니다. 이름으로는 계속 검색할 수 있습니다.';
  const UNFINISHED=/[ㄱ-ㆎ]$/;  // 자음·모음만 있는 미완성 글자(예: '김ㅈ')로 끝나면 아직 치는 중
  const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined&&text!==null)e.textContent=text;if(cls)e.className=cls;return e;};
  async function json(url,signal){
    let response;
    try{response=await fetch(url,{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'},signal});}
    catch(error){if(error.name==='AbortError')throw error;throw new Error(OFFLINE);}
    if(response.redirected)throw new Error('로그인이 만료되었습니다. 다시 로그인하세요.');
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.message||'조회 권한 또는 연결 상태를 확인하세요.');
    return data;
  }
  function scopeOf(value){
    if(value&&value.startsWith('class:'))return {source:'intranet',class_id:value.slice(6)};
    if(value&&value.startsWith('group:'))return {source:'lms',filter_group:value.slice(6)};
    return {source:'all'};
  }
  function row(item,options={}){
    const id=String(item.student_id||item.student_no||'');
    const tag=options.href?'a':(options.checkbox?'label':'div');
    const node=el(tag,null,'st-row'+(options.checkbox?' has-check':'')+(item.selectable===false?' is-unresolved':''));
    node.dataset.studentId=id;node.dataset.search=item.search_text||'';node.dataset.classes=item.class_ids||'';
    if(options.side)node.dataset.side=options.side;
    if(options.href&&item.selectable!==false)node.href=options.href;
    if(options.checkbox){
      const box=document.createElement('input');box.type='checkbox';box.value=id;box.checked=!!options.checked;box.disabled=!!options.disabled;
      if(options.checkName)box.dataset[options.checkName]=options.side||'';
      box.setAttribute('aria-label',`${item.name||id} 선택`);node.append(box);
    }
    const school=item.school_grade||[item.school,item.grade].filter(Boolean).join(' · ');
    const more=el('span',null,'st-more');
    more.append(el('span',school,'st-school'),el('span',item.branch||'','st-branch'),el('span',item.class_label||'','st-classes'));
    node.append(el('strong',item.name||`학생 ${id}`,'st-name'),el('span',id,'st-no'),more);
    const badge=options.badge||(item.selectable===false?'확인 필요':'');
    if(badge)node.append(el('span',badge,'st-badge'));
    node.title=[item.name,id,school,item.branch,item.class_label].filter(Boolean).join(' · ');
    return node;
  }
  // 연결 실패 안내 + 다시 시도. '학생 없음'과 구분되도록 목록 자리에 넣는다.
  function errorBox(message,retry){
    const box=el('div',null,'st-error');box.setAttribute('role','alert');
    box.append(el('p',message||'목록을 불러오지 못했습니다.'));
    if(retry){const button=el('button','다시 시도','ux-btn');button.type='button';button.addEventListener('click',retry);box.append(button);}
    return box;
  }
  function liveInput(input,run,delay=250){
    // 입력이 멈추고 0.25초 뒤 조회한다. 한글 입력기는 마지막 글자를 Enter·Space 전까지 '조합 중'으로 두지만
    // 그 글자도 값에 들어 있으므로 멈추면 조회한다. 미완성 글자로 끝나면 기다리고, 같은 값은 다시 조회하지 않는다
    // (조회 뒤 결과 줄을 누르면 조합이 끝나는데, 그때 다시 그려 체크가 풀리지 않게). Enter는 바로 조회한다.
    let timer=null,last=input.value.trim();
    const fire=()=>{const value=input.value.trim();if(value===last||UNFINISHED.test(value))return;last=value;run();};
    const arm=()=>{clearTimeout(timer);timer=setTimeout(fire,delay);};
    input.addEventListener('input',arm);
    input.addEventListener('compositionend',arm);
    input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing&&e.keyCode!==229){e.preventDefault();clearTimeout(timer);last=input.value.trim();run();}});
    return ()=>clearTimeout(timer);
  }
  function mount(root,options={}){
    if(!root)return null;
    const scopeSelect=root.querySelector('[data-browse-scope]'),q=root.querySelector('[data-browse-q]'),classQ=root.querySelector('[data-class-q]'),
      classFind=root.querySelector('[data-class-find]'),classField=root.querySelector('[data-class-find-field]'),
      pagerRoot=options.pagerRoot||root,textRoot=options.textRoot||root,
      status=root.querySelector('[data-browse-status]'),pageText=textRoot.querySelector('[data-browse-page]'),
      prev=pagerRoot.querySelector('[data-browse-prev]'),next=pagerRoot.querySelector('[data-browse-next]'),allButton=root.querySelector('[data-browse-all]'),
      retry=root.querySelector('[data-browse-retry]');
    let page=1,pages=1,sequence=0,controller=null,optionSeq=0,optionCtl=null,external={source:'all'},optionsFailed=false;
    // 상태 줄 = 학생 목록 상태 + (수업·반 목록이 실패했으면) 그 안내. 두 응답 중 무엇이 먼저 와도 지금 상태로 다시 쓴다.
    let note='';
    const showStatus=()=>{if(status)status.textContent=optionsFailed?(note?`${note} · 수업·반 목록을 불러오지 못했습니다`:OPTIONS_FAILED):note;};
    const say=text=>{note=text;showStatus();};
    // 거르기 막대의 다시 시도는 수업·반 목록이 실패했을 때 보인다. 학생 목록 실패는 목록 자리 안내(errorBox)에 다시 시도가 있다.
    const syncRetry=()=>{if(retry)retry.hidden=!optionsFailed;showStatus();};
    const scope=()=>scopeSelect?scopeOf(scopeSelect.value):external;
    const args=()=>({mode:options.mode||'activity',activity_group:options.getGroup?.()||'',...scope(),q:q?.value.trim()||'',
      grade:root.querySelector('[data-browse-grade]')?.value.trim()||'',school:root.querySelector('[data-browse-school]')?.value.trim()||'',
      size:options.getSize?.()||''});
    const urlFor=(base,values)=>{const u=new URL(base,location.href);if(u.origin!==location.origin)throw new Error('같은 사이트의 주소만 허용됩니다.');for(const [k,v] of Object.entries(values))if(v!==''&&v!==undefined&&v!==null)u.searchParams.set(k,v);return u;};
    // 쪽 번호(11/11): 지금 쪽이 든 10개 묶음 — 눌러서 바로 이동
    const pagesBox=pagerRoot.querySelector('[data-browse-pages]');
    const renderPages=()=>{if(!pagesBox)return;pagesBox.replaceChildren();if(pages<=1)return;
      for(const n of pageList(page,pages)){
        if(n==='…'){const gap=document.createElement('span');gap.className='ux-page-gap';gap.textContent='…';pagesBox.append(gap);continue;}
        const b=document.createElement('button');b.type='button';b.className='ux-page'+(n===page?' is-current':'');b.textContent=String(n);b.setAttribute('aria-label',`${n}쪽`);
        if(n===page)b.setAttribute('aria-current','page');b.addEventListener('click',()=>{if(n!==page){page=n;fetchResults();}});pagesBox.append(b);
      }};
    const pager=(text,hasPrev,hasNext)=>{if(pageText)pageText.textContent=text;if(prev)prev.disabled=!hasPrev;if(next)next.disabled=!hasNext;if(pagesBox){if(hasPrev||hasNext)renderPages();else pagesBox.replaceChildren();}};
    async function fetchResults(all=false){
      const a=args();
      if(options.requireInput&&a.source==='all'&&!a.q&&!all){
        controller?.abort();++sequence;say(options.idleMessage||'조건을 입력하세요.');pager('',false,false);options.onResult?.([],{idle:true});return [];
      }
      controller?.abort();controller=new AbortController();const ctl=controller,seq=++sequence;
      options.onBusy?.(true);say('학생을 불러오는 중…');
      const timeout=setTimeout(()=>ctl.abort(),20000);
      try{
        const data=await json(urlFor(root.dataset.browseUrl,{...a,page,all:all?'1':''}),ctl.signal);
        if(seq!==sequence)return null;
        pages=data.pages||1;syncRetry();
        say(data.message||`${data.total||0}명`);pager(`${page} / ${pages} · 총 ${data.total||0}명`,page>1,page<pages);
        if(!all)options.onResult?.(data.results||[],data);
        return data.results||[];
      }catch(error){
        if(seq!==sequence)return null;
        const message=error.name==='AbortError'?'조회 시간이 초과되었습니다. 다시 조회하세요.':error.message;
        say(message);pager('조회 실패',false,false);
        options.onResult?.([],{total:0,error:true,message,retry:retryAll});options.onError?.(error);
        return null;
      }finally{clearTimeout(timeout);if(seq===sequence)options.onBusy?.(false);}
    }
    async function loadOptions(){
      if(!scopeSelect||!root.dataset.optionsUrl)return;
      optionCtl?.abort();optionCtl=new AbortController();const ctl=optionCtl,seq=++optionSeq;
      let expired=false;const timeout=setTimeout(()=>{expired=true;ctl.abort();},20000);
      try{
        const data=await json(urlFor(root.dataset.optionsUrl,{source:'all',mode:options.mode||'activity',activity_group:options.getGroup?.()||'',q:classQ?.value.trim()||''}),ctl.signal);
        if(seq!==optionSeq)return;
        optionsFailed=false;syncRetry();
        const old=scopeSelect.value,first=scopeSelect.options[0];
        scopeSelect.replaceChildren(first);
        const group=(label,items,prefix,text)=>{if(!items.length)return;const g=document.createElement('optgroup');g.label=label;for(const item of items){const o=el('option',text(item));o.value=prefix+item.id;g.append(o);}scopeSelect.append(g);};
        group('인트라넷 수업',data.classes||[],'class:',c=>c.name+(STATUS[c.status]?` · ${STATUS[c.status]}`:''));
        group('EduTrack 반',data.groups||[],'group:',g=>g.name);
        scopeSelect.value=Array.from(scopeSelect.options).some(o=>o.value===old)?old:'';
        if(classFind)classFind.hidden=!data.has_more&&!(classQ?.value.trim());
        if(scopeSelect.value!==old)reload();
      }catch(e){if(seq===optionSeq&&(expired||e.name!=='AbortError')){optionsFailed=true;syncRetry();}}
      finally{clearTimeout(timeout);}
    }
    function reload(){page=1;return fetchResults();}
    function retryAll(){if(optionsFailed)loadOptions();return fetchResults();}
    scopeSelect?.addEventListener('change',reload);
    const cancelQ=q?liveInput(q,reload):()=>{};
    const cancelClass=classQ?liveInput(classQ,loadOptions):()=>{};
    classFind?.addEventListener('click',()=>{if(classField){classField.hidden=false;classQ?.focus();}});
    root.querySelectorAll('[data-browse-grade],[data-browse-school]').forEach(input=>liveInput(input,reload));
    prev?.addEventListener('click',()=>{if(page>1){page--;fetchResults();}});
    next?.addEventListener('click',()=>{if(page<pages){page++;fetchResults();}});
    retry?.addEventListener('click',retryAll);
    allButton?.addEventListener('click',async()=>{allButton.disabled=true;try{const rows=await fetchResults(true);if(rows)options.onAll?.(rows);}finally{allButton.disabled=false;}});
    window.addEventListener('pagehide',()=>{controller?.abort();optionCtl?.abort();cancelQ();cancelClass();});
    loadOptions();reload();
    return {reload,all:()=>fetchResults(true),reconfigure:()=>{page=1;loadOptions();return reload();},
      setScope:value=>{external=value&&value.source?value:{source:'all'};return reload();}};
  }
  // 로컬 방식: 미리 그린 행(data-search·data-classes)을 브라우저에서 바로 거른다(서버 조회 없음).
  function filterRows(container,{q='',classId='',members=null}={}){
    const needle=String(q).trim().toLocaleLowerCase();let shown=0;
    for(const node of container.querySelectorAll('[data-student-id]')){
      const ok=(!needle||(node.dataset.search||'').includes(needle))
        &&(!classId||(node.dataset.classes||'').split(' ').includes(classId))
        &&(!members||members.has(node.dataset.studentId));
      node.hidden=!ok;if(ok)shown++;
    }
    return shown;
  }
  function scopeFilter(select){
    const value=select?.value||'',option=select?.selectedOptions?.[0];
    if(value.startsWith('class:'))return {classId:value.slice(6)};
    if(value.startsWith('group:'))return {members:new Set((option?.dataset.members||'').split(' ').filter(Boolean))};
    return {};
  }
  function mountLocal(root){
    const select=root.querySelector('[data-local-scope]'),q=root.querySelector('[data-local-q]'),rows=root.querySelector('[data-local-rows]'),
      status=root.querySelector('[data-local-status]'),empty=root.querySelector('[data-local-empty]');
    if(!rows)return;
    const total=rows.querySelectorAll('[data-student-id]').length,unresolved=rows.querySelectorAll('.is-unresolved').length;
    const apply=()=>{
      const shown=filterRows(rows,{q:q?.value||'',...scopeFilter(select)});
      if(empty){empty.hidden=shown>0;if(!shown&&total)empty.textContent='조건에 맞는 담당 학생이 없습니다.';}
      if(status)status.textContent=`${shown}명 표시 / 담당 학생 ${total}명`+(unresolved?` · ${unresolved}명은 학생번호 확인 필요`:'');
    };
    select?.addEventListener('change',apply);
    if(q)liveInput(q,apply,120);
    apply();
  }
  // 관리자 학생 관리(11/11): 인트라넷 '학생 리스트'처럼 표 + 20·50·100명 + 맨 아래 가운데 쪽 이동.
  function dirRow(item,n,pattern){
    const tr=document.createElement('tr');tr.dataset.studentId=String(item.student_id||'');
    const td=(text,cls)=>{const c=el('td',text===undefined||text===null||text===''?'-':String(text),cls);tr.append(c);return c;};
    td(n,'st-dir-n');td(item.student_id,'st-dir-id');
    const nameCell=document.createElement('td'),link=el('a',item.name||'(이름 없음)','st-dir-name');
    link.href=pattern.replace('__ID__',encodeURIComponent(item.student_id));nameCell.append(link);tr.append(nameCell);
    td(item.branch);td(item.grade);td(item.school,'st-dir-school');td(item.country);td(item.city);
    const st=document.createElement('td');
    if(item.status){st.append(el('span',item.status,'st-dir-status'+(item.status!=='재원'?' is-off':'')));}else st.textContent='-';
    tr.append(st);td(item.class_label,'st-dir-classes');return tr;
  }
  function mountDirectory(root){
    const table=root.querySelector('[data-remote-rows]');if(!table)return;
    const body=table.tBodies?.[0]||table,pattern=table.dataset.detailUrl||'',sizeSelect=root.querySelector('[data-page-size]'),
      totalBox=root.querySelector('[data-dir-total] b'),pagerBox=root.querySelector('[data-directory-pager]');
    let shownPage=1;
    const fullRow=node=>{const tr=document.createElement('tr');tr.className='st-dir-empty';const c=document.createElement('td');c.colSpan=10;c.append(node);tr.append(c);return tr;};
    // 검색어가 없어도 전체 학생 첫 쪽을 바로 불러옵니다(인트라넷 학생 목록처럼).
    const api=mount(root.querySelector('[data-student-browser]'),{requireInput:false,pagerRoot:pagerBox||root,textRoot:root,
      getSize:()=>sizeSelect?.value||'20',
      onResult:(rows,meta)=>{
        const size=meta?.page_size||Number(sizeSelect?.value)||20,page=meta?.page||1;
        body.replaceChildren(...rows.map((item,i)=>dirRow(item,(page-1)*size+i+1,pattern)));
        if(totalBox&&meta&&!meta.error)totalBox.textContent=String(meta.total??0);
        if(meta?.error)body.append(fullRow(errorBox(meta.message,meta.retry)));
        else if(!rows.length&&!meta?.idle)body.append(fullRow(el('span','조건에 맞는 학생이 없습니다.')));
        // 맨 아래에서 쪽을 넘기면 표 머리로 올려 줍니다.
        if(page!==shownPage&&table.getBoundingClientRect().top<0)table.scrollIntoView({block:'start'});
        shownPage=page;
      }});
    // 보기 개수는 주소(size)에 남겨 새로고침해도 유지합니다(브라우저 저장소는 쓰지 않음).
    sizeSelect?.addEventListener('change',()=>{try{const u=new URL(location.href);u.searchParams.set('size',sizeSelect.value);history.replaceState(null,'',u);}catch(e){}api?.reload();});
  }
  // 쪽 번호는 10개씩 묶어 보여 줍니다(11/11): 1~10, 10을 넘어가면 11~20 (인트라넷 학생 리스트와 같게).
  function pageList(page,pages){
    const start=Math.floor((Math.max(1,page)-1)/10)*10+1,end=Math.min(pages,start+9);
    return Array.from({length:Math.max(0,end-start+1)},(_,i)=>start+i);
  }
  window.EduStudentBrowser={mount,row,scopeOf,liveInput,filterRows,errorBox,pageList};
  document.querySelectorAll('[data-local-student-list]').forEach(mountLocal);
  document.querySelectorAll('[data-student-directory]').forEach(mountDirectory);
})();
