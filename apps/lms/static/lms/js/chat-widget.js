/* Modeless, draggable messenger. Uses existing authenticated endpoints; no iframe or HTML injection. */
(() => {
 'use strict';
 const root=document.querySelector('[data-chat-widget]'),tools=window.EduTrackPolling;
 if(!root || !tools || window.EduTrackMiniChat)return;
 const $=s=>root.querySelector(s),win=$('[data-chat-window]'),log=$('[data-chat-log]'),form=$('[data-chat-form]'),input=form.querySelector('textarea');
 const state={id:null,last:0,before:null,api:null,epoch:0,feed:null,loading:null,sending:false,readBusy:false,ack:0,blocked:false};
 const drafts=new Map(),pendingSends=new Map(),ids=new Set();let summaryData=null,summarySig='',opener=null,position=null;
 const bell=document.querySelector('[data-portal-bell]'),bellBox=document.getElementById('portal-notification-box');
 const status=$('[data-chat-status]'),threads=$('[data-chat-threads]'),thread=$('[data-chat-thread]');
 const csrf=()=>form.querySelector('[name=csrfmiddlewaretoken]').value;
 const nearBottom=()=>log.scrollHeight-log.scrollTop-log.clientHeight<60;
 const setStatus=t=>{status.textContent=t;};
 const sameOrigin=url=>{try{const u=new URL(url,location.origin);return u.origin===location.origin?u.pathname+u.search:null;}catch(_){return null;}};
 const snapshotUrl=id=>root.dataset.snapshot.replace(/\/0\/snapshot\/$/,`/${id}/snapshot/`);
 const positionKey=`edutrack:chat-position:${root.dataset.user}`;
 try{const p=JSON.parse(sessionStorage.getItem(positionKey));if(p&&Number.isFinite(p.x)&&Number.isFinite(p.y))position=p;}catch(_){}
 function fit(){
   if(matchMedia('(max-width:700px)').matches){win.style.left='';win.style.top='';win.style.right='';win.style.bottom='';return;}
   if(!position)return;
   const rect=win.getBoundingClientRect(),x=Math.max(8,Math.min(position.x,innerWidth-rect.width-8)),y=Math.max(8,Math.min(position.y,innerHeight-rect.height-8));
   position={x,y};win.style.left=x+'px';win.style.top=y+'px';win.style.right='auto';win.style.bottom='auto';
 }
 function savePosition(){try{sessionStorage.setItem(positionKey,JSON.stringify(position));}catch(_){}}
 function remember(){if(state.id)drafts.set(state.id,{body:input.value,token:form.querySelector('[name=client_token]').value});}
 function stopThread(){state.epoch++;state.feed?.dispose();state.feed=null;state.loading?.abort();state.loading=null;}
 function close(){remember();stopThread();win.hidden=true;bellBox&&(bellBox.hidden=true);bell?.setAttribute('aria-expanded','false');opener?.focus?.({preventScroll:true});}
 function show(){opener=document.activeElement;win.hidden=false;fit();if(bellBox)bellBox.hidden=true;bell?.setAttribute('aria-expanded','false');}
 // 안 읽은 수가 늘었을 때만 숫자를 한 번 튀게 해 새 메시지를 알립니다 (움직임 줄이기 설정이면 CSS에서 꺼짐).
 function setCount(e,text){
   if(Number(text)>Number(e.textContent)){e.classList.remove('is-bumped');void e.offsetWidth;e.classList.add('is-bumped');}
   e.textContent=text;
 }
 function markCounts(data){
   document.querySelectorAll('[data-chat-count],[data-unread-count]').forEach(e=>setCount(e,String(data.unread_count)));
   document.querySelectorAll('[data-portal-total]').forEach(e=>{setCount(e,data.total_unread>99?'99+':String(data.total_unread));e.hidden=!data.total_unread;});
   document.querySelectorAll('[data-notice-count]').forEach(e=>e.textContent=String(data.notification_count));
   bell?.setAttribute('aria-label',`알림: 안 읽은 대화 ${data.unread_count}개, 학습 알림 ${data.notification_count}개`);
 }
 function preview(item){
   const a=document.createElement('a');a.href=sameOrigin(item.url)||root.dataset.inbox;a.dataset.conversationId=String(item.id);a.className='portal-message-preview'+(item.unread?' unread':'');
   const d=document.createElement('div'),name=document.createElement('strong'),p=document.createElement('p'),badge=document.createElement('span');
   name.textContent=item.title;p.textContent=item.preview;badge.textContent=item.unread?'안 읽음':item.time;d.append(name,p);a.append(d,badge);return a;
 }
 function listRender(node,items,empty){
   const focus=document.activeElement?.closest('[data-conversation-id]')?.dataset.conversationId;
   node.replaceChildren(...items.map(preview));if(!items.length){const p=document.createElement('p');p.className='portal-empty';p.textContent=empty;node.append(p);}
   if(focus)node.querySelector(`[data-conversation-id="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
 }
 function updateSummary(data){
   summaryData=data;markCounts(data);const signature=JSON.stringify([data.items,data.unread_items]);
   if(signature!==summarySig){
     summarySig=signature;
     listRender(threads,data.items,'아직 참여 중인 대화가 없습니다. 새 대화를 시작하세요.');
     document.querySelectorAll('[data-home-chat-list]').forEach(n=>listRender(n,data.items.slice(0,5),'새 대화는 메신저의 ＋ 새 대화에서 시작할 수 있습니다.'));
     const unread=data.unread_items || data.items.filter(i=>i.unread);
     document.querySelectorAll('[data-chat-mini-list]').forEach(n=>listRender(n,unread,'안 읽은 메시지가 없습니다.'));
   }
 }
 function block(error){
   state.blocked=true;stopThread();state.id=null;input.value='';drafts.clear();pendingSends.clear();log.replaceChildren();threads.replaceChildren();
   document.querySelectorAll('[data-home-chat-list],[data-chat-mini-list]').forEach(n=>n.replaceChildren());
   document.querySelectorAll('[data-chat-count],[data-portal-total]').forEach(e=>e.textContent='—');
   form.querySelector('button[type=submit]').disabled=true;setStatus(error.message);
 }
 const summaryPoll=tools.start(async signal=>{const data=await tools.json(root.dataset.summary,{signal});if(!signal.aborted)updateSummary(data);},(e,terminal)=>{if(terminal)block(e);else setStatus('연결 확인 중입니다. 입력 내용은 유지됩니다.');},true);
 // 그룹 대화·반 단체방은 제목 아래에 참여자 명단을 바로 보여 줍니다(1:1은 숨김).
 function showMembers(names){const box=$('[data-mini-members]');if(!box)return;const list=Array.isArray(names)?names:[];box.hidden=!list.length;box.textContent=list.length?`참여자 ${list.length}명 · ${list.join(', ')}`:'';box.title=list.join(', ');}
 function listOpen(){remember();stopThread();state.id=null;show();showMembers([]);thread.hidden=true;threads.hidden=false;$('[data-chat-new]').hidden=false;$('[data-chat-back]').hidden=true;$('#portal-chat-title').textContent='메신저';$('[data-chat-expand]').href=root.dataset.inbox;setStatus('새 메시지를 5초 간격으로 확인합니다.');summaryPoll.refresh();$('[data-chat-close]').focus({preventScroll:true});}
 function append(row,container=log){
   if(ids.has(row.id))return null;ids.add(row.id);
   const e=document.createElement('article');e.className='portal-chat-message'+(row.own?' own':'');e.dataset.messageId=String(row.id);
   const sender=document.createElement('small'),body=document.createElement('p'),time=document.createElement('time');sender.textContent=row.sender;body.textContent=row.body;time.textContent=row.time;e.append(sender,body,time);container.append(e);return e;
 }
 async function acknowledge(){
   if(state.readBusy||!state.id||!state.api||win.hidden||document.hidden||!nearBottom()||state.last<=state.ack)return;
   const id=state.id,target=state.last,epoch=state.epoch;state.readBusy=true;
   try{await tools.json(state.api.read_url,{method:'POST',headers:{'X-CSRFToken':csrf()},body:new URLSearchParams({up_to:String(target)})});if(id===state.id&&epoch===state.epoch){state.ack=target;summaryPoll.refresh();}}
   catch(e){if(e.terminal&&epoch===state.epoch)block(e);}
   finally{state.readBusy=false;}
 }
 function feedStart(){
   const epoch=state.epoch;
   state.feed=tools.start(async signal=>{
     if(win.hidden||!state.id)return;
     const data=await tools.json(`${state.api.feed_url}?after=${state.last}`,{signal});if(signal.aborted||epoch!==state.epoch)return;
     const bottom=nearBottom();let added=false;
     for(const row of data.messages){if(!Number.isSafeInteger(row.id)||row.id<=state.last)continue;append(row);state.last=row.id;added=true;}
     if(bottom){log.scrollTop=log.scrollHeight;$('[data-chat-jump]').hidden=true;acknowledge();}
     else if(added)$('[data-chat-jump]').hidden=false;
     if(!state.sending)setStatus('새 메시지 자동 확인 · 3초 간격');
     return {catchUp:!!data.has_more};
   },(e,terminal)=>{if(terminal)block(e);else setStatus(e.message);},false,{interval:3000});
 }
 async function open(id){
   id=Number(id);if(!Number.isSafeInteger(id)||id<1||state.blocked)return;
   if(state.id===id&&!win.hidden&&state.api){input.focus();return;}
   remember();stopThread();show();state.id=id;state.last=0;state.ack=0;state.before=null;state.api=null;
   const epoch=state.epoch;threads.hidden=true;thread.hidden=false;$('[data-chat-new]').hidden=true;$('[data-chat-back]').hidden=false;
   $('#portal-chat-title').textContent='대화 불러오는 중…';log.replaceChildren();ids.clear();input.value=drafts.get(id)?.body||'';form.querySelector('button[type=submit]').disabled=true;
   $('[data-chat-older]').hidden=true;setStatus('대화를 확인하고 있습니다.');state.loading=new AbortController();
   try{
     const data=await tools.json(snapshotUrl(id),{signal:state.loading.signal});if(epoch!==state.epoch)return;
     if(![data.url,data.feed_url,data.read_url].every(sameOrigin))throw new Error('대화 주소를 확인하지 못했습니다.');
     state.api=data;state.last=data.last_id;state.before=data.before;
     for(const row of data.messages)append(row);
     form.querySelector('[name=client_token]').value=drafts.get(id)?.token||data.client_token;
     $('#portal-chat-title').textContent=data.title;showMembers(data.members);$('[data-chat-expand]').href=data.url;$('[data-chat-older]').hidden=!data.before;
     form.querySelector('button[type=submit]').disabled=false;log.scrollTop=log.scrollHeight;input.focus({preventScroll:true});feedStart();acknowledge();setStatus('새 메시지 자동 확인 · 5초 간격');
   }catch(e){if(epoch!==state.epoch||e.name==='AbortError')return;if(e.terminal)block(e);else setStatus(e.message);}
 }
 form.addEventListener('submit',async e=>{
   e.preventDefault();if(state.sending||!state.api||state.blocked)return;
   const text=input.value;if(!text.trim()){input.focus();return;}
   const id=state.id,epoch=state.epoch,api=state.api,button=form.querySelector('button[type=submit]'),payload=new FormData(form);
   const attempt=pendingSends.get(id)||{body:text,token:payload.get('client_token')};pendingSends.set(id,attempt);
   // A lost success response must retry the exact original token/body, not erase a newer draft.
   payload.set('body',attempt.body);payload.set('client_token',attempt.token);
   remember();state.sending=true;button.disabled=true;setStatus('전송 중…');
   try{
     const data=await tools.json(api.url,{method:'POST',body:payload,signal:AbortSignal.timeout(15000)});
     pendingSends.delete(id);const old=drafts.get(id);drafts.set(id,{body:old?.body===attempt.body?'':(old?.body||''),token:data.client_token});
     if(state.id===id&&epoch===state.epoch){form.querySelector('[name=client_token]').value=data.client_token;if(input.value===attempt.body)input.value='';remember();state.feed?.refresh();setStatus(attempt.body===text?'메시지를 보냈습니다.':'이전 전송 확인 완료. 작성한 새 내용은 Enter로 보내세요.');}
     summaryPoll.refresh();
   }catch(error){if(id===state.id&&epoch===state.epoch){if(error.terminal)block(error);else setStatus('전송을 확인하지 못했습니다. 내용은 유지됩니다. 다시 전송하세요.');}}
   finally{state.sending=false;if(!state.blocked&&state.api)button.disabled=false;}
 });
 window.EduChatComposer?.bind(form,input);
 $('[data-chat-older]').addEventListener('click',async()=>{
   if(!state.before||!state.api)return;const epoch=state.epoch,b=$('[data-chat-older]');b.disabled=true;
   try{const data=await tools.json(`${snapshotUrl(state.id)}?before=${state.before}`);if(epoch!==state.epoch)return;const old=log.scrollHeight,top=log.scrollTop,fragment=document.createDocumentFragment();for(const row of data.messages)append(row,fragment);log.prepend(fragment);log.scrollTop=top+(log.scrollHeight-old);state.before=data.before;b.hidden=!data.before;}
   catch(e){setStatus(e.message);}finally{b.disabled=false;}
 });
 log.addEventListener('scroll',()=>{if(nearBottom()){acknowledge();$('[data-chat-jump]').hidden=true;}},{passive:true});
 $('[data-chat-jump]').addEventListener('click',()=>{log.scrollTop=log.scrollHeight;acknowledge();$('[data-chat-jump]').hidden=true;});
 $('[data-chat-back]').addEventListener('click',listOpen);$('[data-chat-close]').addEventListener('click',close);
 $('[data-chat-reset]').addEventListener('click',()=>{position=null;try{sessionStorage.removeItem(positionKey);}catch(_){}win.style.cssText='';fit();});
 document.addEventListener('click',e=>{
   if(e.defaultPrevented||e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;
   const element=e.target.closest('a,button');if(!element)return;
   // 작은 메신저는 자기 영역 안(둥근 버튼·대화 목록)의 클릭만 맡습니다. 머리글·홈의 '메시지' 링크는 메시지 페이지로 이동합니다(11/16).
   if(root.contains(element)){
     const conv=element.dataset.conversationId;
     if(conv){e.preventDefault();open(conv);return;}
     if(element.matches('[data-chat-launch]')){e.preventDefault();listOpen();}
   }
   if(bellBox&&!bellBox.hidden&&!bellBox.contains(e.target)&&!bell?.contains(e.target)){bellBox.hidden=true;bell?.setAttribute('aria-expanded','false');}
 });
 bell?.addEventListener('click',()=>{bellBox.hidden=!bellBox.hidden;bell.setAttribute('aria-expanded',String(!bellBox.hidden));if(!bellBox.hidden)summaryPoll.refresh();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(bellBox&&!bellBox.hidden){bellBox.hidden=true;bell.setAttribute('aria-expanded','false');bell.focus();}else if(!win.hidden)close();}});
 const handle=$('[data-chat-drag]');let moving=null;
 handle.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button,a')||matchMedia('(max-width:700px)').matches)return;const rect=win.getBoundingClientRect();moving={x:e.clientX,y:e.clientY,left:rect.left,top:rect.top};handle.setPointerCapture(e.pointerId);});
 handle.addEventListener('pointermove',e=>{if(!moving)return;position={x:moving.left+e.clientX-moving.x,y:moving.top+e.clientY-moving.y};fit();});
 const endMove=()=>{moving=null;savePosition();};handle.addEventListener('pointerup',endMove);handle.addEventListener('pointercancel',endMove);
 handle.addEventListener('keydown',e=>{if(e.target!==handle||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const rect=win.getBoundingClientRect();position={x:rect.left+({ArrowLeft:-20,ArrowRight:20}[e.key]||0),y:rect.top+({ArrowUp:-20,ArrowDown:20}[e.key]||0)};fit();savePosition();});
 window.addEventListener('resize',fit);window.visualViewport?.addEventListener('resize',fit);
 window.addEventListener('edutrack:chat-read',()=>summaryPoll.refresh());
 window.addEventListener('beforeunload',e=>{remember();if([...drafts.values()].some(d=>d.body.trim())){e.preventDefault();e.returnValue='';}});
 window.EduTrackMiniChat={open,listOpen,close,refresh:()=>summaryPoll.refresh()};
})();
