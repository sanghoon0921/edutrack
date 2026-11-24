/* Chat page (카카오톡식): 날짜 구분선, 같은 사람·같은 분 메시지 묶음, 안 읽은 사람 수, 위로 올리면 이전 메시지 자동 불러오기.
   Bounded short polling compatible with the existing Waitress runner. 서버 쪽 모양: apps/lms/rooms.message_row, templates lms/_message.html */
(() => {
 'use strict';
 const list=document.getElementById('lms-message-list'),tools=window.EduTrackPolling;
 if(!list||!tools)return;
 const form=document.getElementById('lms-message-form'),status=document.getElementById('message-status'),jump=document.getElementById('message-jump'),textarea=form.querySelector('[name=body]'),button=form.querySelector('[type=submit]'),token=form.querySelector('[name=client_token]');
 const csrf=()=>form.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
 const ids=new Set(Array.from(list.querySelectorAll('[data-message-id]')).map(e=>Number(e.dataset.messageId)));
 let marks=[];try{marks=JSON.parse(document.getElementById('lms-read-marks')?.textContent||'[]');}catch(_){}
 let last=Number(list.dataset.lastId)||0,sending=false,terminal=false,ack=0,ackBusy=false,pending=null;
 const active=list.dataset.poll==='true',atBottom=()=>list.scrollHeight-list.scrollTop-list.clientHeight<72;
 const messages=()=>Array.from(list.querySelectorAll('[data-message-id]'));
 function error(e){status.textContent=e.message;if(e.terminal){terminal=true;button.disabled=true;poller?.stop();}}

 // 안 읽은 사람 수: 보낸 사람·나를 뺀 참여자 중 이 메시지 뒤에 들어온 것도 아니고 아직 읽지 않은 사람.
 function unread(node){const id=Number(node.dataset.messageId),sender=Number(node.dataset.sender);return marks.filter(m=>m.u!==sender&&m.j<id&&m.r<id).length;}
 function paintUnread(){for(const node of messages()){const b=node.querySelector('.kt-unread');if(!b)continue;const n=unread(node);b.textContent=String(n);b.hidden=!n;b.setAttribute('aria-label',`안 읽은 사람 ${n}명`);}}
 // 같은 사람이 같은 분에 이어 보낸 메시지는 이름을 처음에만, 시간을 마지막에만.
 const sameRun=(a,b)=>a&&b&&a.dataset.sender===b.dataset.sender&&a.dataset.minute===b.dataset.minute&&a.dataset.day===b.dataset.day;
 function regroup(){
  const nodes=messages();
  nodes.forEach((node,i)=>{node.classList.toggle('is-first',!sameRun(nodes[i-1],node));node.classList.toggle('is-last',!sameRun(node,nodes[i+1]));});
  list.querySelectorAll('.kt-day').forEach(d=>d.remove());
  let day='';for(const node of nodes){if(node.dataset.day!==day){day=node.dataset.day;const sep=document.createElement('div');sep.className='kt-day';sep.dataset.day=day;const s=document.createElement('span');s.textContent=day;sep.append(s);node.before(sep);}}
 }
 function build(m){
  const article=document.createElement('article');article.className='lms-message kt-msg'+(m.own?' own':'');
  Object.assign(article.dataset,{messageId:m.id,sender:m.sender_id,minute:m.minute,day:m.day});
  if(!m.own){const name=document.createElement('strong');name.className='kt-name';name.textContent=m.sender;article.append(name);}
  const line=document.createElement('div'),bubble=document.createElement('p'),meta=document.createElement('span'),count=document.createElement('b'),time=document.createElement('time');
  line.className='kt-line';bubble.className='kt-bubble';meta.className='kt-meta';count.className='kt-unread';
  bubble.textContent=m.body;time.textContent=m.time;meta.append(count,time);line.append(bubble,meta);article.append(line);
  return article;
 }
 function append(m){
  if(ids.has(m.id))return;ids.add(m.id);list.querySelector('[data-empty]')?.remove();
  const later=messages().find(n=>Number(n.dataset.messageId)>m.id);
  list.insertBefore(build(m),later||null);
 }
 function settle(){regroup();paintUnread();}
 async function read(){if(ackBusy||!last||ack>=last||document.hidden||!atBottom()||!active)return;const target=last;ackBusy=true;try{await tools.json(list.dataset.readUrl,{method:'POST',headers:{'X-CSRFToken':csrf()},body:new URLSearchParams({up_to:target}),signal:AbortSignal.timeout(10000)});ack=target;window.dispatchEvent(new Event('edutrack:chat-read'));}catch(_){/* Do not mark home previews as read. */}finally{ackBusy=false;}}
 const size=()=>{textarea.style.height='auto';textarea.style.height=Math.min(112,Math.max(48,textarea.scrollHeight))+'px';};
 textarea.setAttribute('enterkeyhint','send');textarea.addEventListener('input',size);size();
 // 한글 조합 중 Enter도 한 번에 전송 (공용 처리: lms/js/chat-composer.js)
 window.EduChatComposer?.bind(form,textarea);
 list.scrollTop=list.scrollHeight;
 const poller=active?tools.start(async signal=>{
  const data=await tools.json(`${list.dataset.feedUrl}?after=${last}`,{signal});if(signal.aborted||document.hidden)return;
  const follow=atBottom();let added=false;
  for(const m of data.messages){if(!Number.isSafeInteger(m.id)||m.id<=last)continue;append(m);last=m.id;added=true;}
  if(Array.isArray(data.read_marks))marks=data.read_marks;
  settle();
  if(follow){list.scrollTop=list.scrollHeight;jump.hidden=true;read();}else if(added)jump.hidden=false;
  if(!sending&&!pending)status.textContent='새 메시지 자동 확인 중';return {catchUp:!!data.has_more};
 },error,true,{interval:2000}):null;
 if(!active)status.textContent='이전 기록입니다. 최근 메시지로 이동하면 자동 갱신됩니다.';
 jump.addEventListener('click',()=>{list.scrollTop=list.scrollHeight;jump.hidden=true;read();});
 // 맨 위 가까이 올리면 이전 메시지를 자동으로 불러옵니다(버튼은 키보드·스크립트 없는 경우용).
 const older=list.querySelector('[data-chat-older]');let oldBusy=false;
 async function loadOlder(){
  if(!active||!older||older.hidden||oldBusy)return;oldBusy=true;
  const h=list.scrollHeight,y=list.scrollTop;
  try{const data=await tools.json(`${list.dataset.feedUrl}?before=${older.dataset.before}`,{signal:AbortSignal.timeout(12000)});for(const m of data.messages)append(m);settle();list.prepend(older);list.scrollTop=y+(list.scrollHeight-h);if(data.messages.length)older.dataset.before=data.messages[0].id;older.hidden=!data.has_more;}
  catch(e){error(e);}finally{oldBusy=false;}
 }
 older?.addEventListener('click',event=>{if(!active)return;event.preventDefault();loadOlder();});
 list.addEventListener('scroll',()=>{if(atBottom()){jump.hidden=true;read();}if(list.scrollTop<80)loadOlder();},{passive:true});
 form.addEventListener('submit',async event=>{
  if(!active)return;event.preventDefault();if(sending||terminal)return;
  const current=textarea.value;if(!pending&&!current.trim()){status.textContent='메시지를 입력하세요.';textarea.focus();return;}
  // Retrying an uncertain request uses the exact original body and token.
  if(!pending)pending={body:current,token:token.value};
  const snapshot=pending,body=new FormData(form);body.set('body',snapshot.body);body.set('client_token',snapshot.token);
  sending=true;button.disabled=true;status.textContent='전송 중…';
  try{
   const data=await tools.json(location.pathname,{method:'POST',body,signal:AbortSignal.timeout(15000)});
   token.value=data.client_token;pending=null;
   if(data.message){append(data.message);settle();} // Own message appears immediately, after save confirmation.
   // Keep the old receive cursor so missed incoming messages are not skipped.
   if(textarea.value===snapshot.body)textarea.value='';size();list.scrollTop=list.scrollHeight;
   status.textContent='전송됨';poller.refresh();window.dispatchEvent(new Event('edutrack:chat-read'));textarea.focus();
  }catch(e){error(e);if(!terminal)status.textContent='전송 확인 실패 · 입력은 유지됩니다. 보내기를 다시 누르면 중복 없이 확인합니다.';}
  finally{sending=false;button.disabled=terminal;button.textContent=pending?'다시 전송':'보내기';}
 });
 settle();
})();
