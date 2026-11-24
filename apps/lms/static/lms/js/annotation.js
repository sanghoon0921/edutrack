/* 첨삭 화면(Canvas SpeedGrader 방식): 도구·색·굵기를 고르고 문서에 표시하면 문서 밖 오른쪽 여백에 설명 입력칸이 뜹니다.
   쓴 설명은 여백의 말풍선으로 남아 점선으로 번호와 이어지고(학생 화면도, 본문을 가리지 않음), 오른쪽 카드에서도 같은 설명을 고칠 수 있습니다.
   mode 'review'  : '의견 제출' 양식(data-grader-form)이 첨삭을 점수·총평과 함께 보냅니다. 실패하면 이 탭에 남긴 첨삭을 다시 불러옵니다.
   mode 'document': '첨삭 저장·공개' 버튼(#ann-save)으로 첨삭만 따로 저장합니다(퀴즈 답안·이전 제출 화면). */
(() => {
  'use strict';
  const root=document.getElementById('annotation-editor');
  if(!root) return;
  const data=JSON.parse(document.getElementById('lms-document-data').textContent);
  const $=id=>document.getElementById(id);
  const image=$('ann-image'),svg=$('ann-overlay'),paper=$('ann-paper'),list=$('ann-list'),status=$('ann-status'),count=$('ann-count');
  const NS='http://www.w3.org/2000/svg';
  const labels=Object.fromEntries(data.tools.map(t=>[t.id,t.label]));
  const form=document.querySelector('form[data-grader-form]');
  const draftKey=`edutrack:annotation-draft:${data.documentId}`;
  const pendingText=data.mode==='review'?'바뀐 첨삭은 의견 제출을 누르면 저장됩니다.':'바뀐 첨삭은 첨삭 저장·공개를 누르면 저장됩니다.';
  let marks=structuredClone(data.annotations),revision=data.revision,page=1,dirty=false,history=[],draft=null,drawStart=null,changeNo=0,saving=false,active=null;
  let tool=data.tools[0].id,color=data.colors[0].hex,width=4,size=20,viewW=1000,viewH=1400;
  // 글자 층: 이 쪽 단어 위치(서버 page_words). 형광펜·취소선은 단어 위에서 누르면 글자 단위로 고릅니다.
  let words=[],textPick=null,inlineBox=null,inlineId=null,commentBox=null,commentId=null;
  // 문서 밖 오른쪽 여백(운영팀 요청 10.29): 설명 말풍선·입력칸은 번호와 같은 높이에 놓고 점선으로 잇습니다. 겹치면 아래로 밀어 냅니다.
  const stage=document.createElement('div');stage.className='ann-stage';paper.before(stage);stage.append(paper);
  const margin=document.createElement('div');margin.className='ann-margin';stage.append(margin);
  const links=document.createElementNS(NS,'svg');links.setAttribute('class','ann-links');links.setAttribute('aria-hidden','true');stage.append(links);
  let placed=[];
  const TEXT_TOOLS=new Set(['highlight','strikeout']);
  const inBox=(w,p,pad=0.004)=>p[0]>=w.x-pad&&p[0]<=w.x+w.w+pad&&p[1]>=w.y-pad*1.5&&p[1]<=w.y+w.h+pad*1.5;
  const wordAt=p=>words.findIndex(w=>inBox(w,p));
  function nearestWord(p){
    const hit=wordAt(p);if(hit>=0)return hit;
    let best=-1,dist=0.05;
    words.forEach((w,i)=>{const dx=Math.max(w.x-p[0],0,p[0]-(w.x+w.w)),dy=Math.max(w.y-p[1],0,p[1]-(w.y+w.h));const d=Math.hypot(dx,dy*1.5);if(d<dist){dist=d;best=i;}});
    return best;
  }
  function pickedRects(a,b){
    const [from,to]=a<=b?[a,b]:[b,a],lines=new Map();
    for(const w of words.slice(from,to+1)){const r=lines.get(w.line);if(!r)lines.set(w.line,[w.x,w.y,w.x+w.w,w.y+w.h]);else{r[0]=Math.min(r[0],w.x);r[1]=Math.min(r[1],w.y);r[2]=Math.max(r[2],w.x+w.w);r[3]=Math.max(r[3],w.y+w.h);}}
    const round=v=>Math.round(v*1e6)/1e6;
    return [...lines.values()].map(([x0,y0,x1,y1])=>{const pad=(y1-y0)*0.15,y=Math.max(0,y0-pad),h=Math.min(1-y,y1-y0+pad*2);return [round(x0),round(y),round(Math.min(1-x0,x1-x0)),round(h)];});
  }
  function applyPick(mark){
    const [from,to]=textPick.start<=textPick.end?[textPick.start,textPick.end]:[textPick.end,textPick.start];
    mark.rects=pickedRects(from,to);mark.quote=words.slice(from,to+1).map(w=>w.t).join(' ').slice(0,1000);
    const xs=mark.rects.map(r=>r[0]),ys=mark.rects.map(r=>r[1]);
    mark.x=Math.min(...xs);mark.y=Math.min(...ys);mark.w=Math.max(...mark.rects.map(r=>r[0]+r[2]))-mark.x;mark.h=Math.max(...mark.rects.map(r=>r[1]+r[3]))-mark.y;
  }

  const setStatus=(text,error=false)=>{status.textContent=text;status.classList.toggle('is-error',error);};
  const remember=()=>{history.push(structuredClone(marks));if(history.length>40)history.shift();dirty=true;changeNo++;};
  const onPage=()=>marks.filter(m=>m.page===page);
  // 첨삭 표시 id(UUID v4). 사무실 서버 주소(http://192.168.x.x)는 보안 연결이 아니라 crypto.randomUUID 가 없으므로 getRandomValues 로 만듭니다.
  const newId=()=>{const b=crypto.getRandomValues(new Uint8Array(16));b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=[...b].map(x=>x.toString(16).padStart(2,'0')).join('');return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;};
  function el(tag,attrs={},text){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
  // 번호 글씨색(11/11): 노랑처럼 밝은 첨삭 색 위에서는 흰 글씨가 안 보여서 진한 글씨로.
  const ink=c=>{const m=/^#?([0-9a-f]{6})$/i.exec(String(c||''));if(!m)return '#fff';const n=parseInt(m[1],16),f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4);};
    const L=.2126*f(n>>16&255)+.7152*f(n>>8&255)+.0722*f(n&255);return L>.42?'#1f2937':'#fff';};
  function badge(g,x,y,c,label){g.append(el('circle',{cx:Math.max(10,x),cy:Math.max(10,y),r:9,fill:c}),el('text',{x:Math.max(10,x),y:Math.max(10,y)+4,fill:ink(c),'font-size':11,'font-weight':700,'text-anchor':'middle'},label));}

  function showMark(m,index){
    const x=m.x*viewW,y=m.y*viewH,w=m.w*viewW,h=m.h*viewH,c=m.color,stroke=m.width||4,label=String(index+1);
    const g=el('g',{'data-annotation-id':m.id,class:'ann-mark'+(m.id===active?' is-active':'')});
    if(m.type==='point')g.append(el('circle',{cx:x,cy:y,r:11,fill:c}),el('text',{x,y:y+4,fill:ink(c),'font-size':12,'font-weight':700,'text-anchor':'middle'},label));
    if(m.rects&&(m.type==='highlight'||m.type==='strikeout')){
      // 글자를 드래그해 그은 표시: 줄마다 형광펜 칸 또는 가운데 취소선.
      for(const [rx,ry,rw,rh] of m.rects){
        const X=rx*viewW,Y=ry*viewH,W=rw*viewW,H=rh*viewH;
        g.append(m.type==='highlight'?el('rect',{x:X,y:Y,width:W,height:H,fill:c,opacity:0.3,rx:2}):el('line',{x1:X,y1:Y+H/2,x2:X+W,y2:Y+H/2,stroke:c,'stroke-width':stroke,'stroke-linecap':'round'}));
      }
      badge(g,m.rects[0][0]*viewW,m.rects[0][1]*viewH,c,label);
    }
    else if(m.type==='highlight'){g.append(el('rect',{x,y,width:w,height:h,fill:c,opacity:0.28}));badge(g,x,y,c,label);}
    if(m.type==='area'){g.append(el('rect',{x,y,width:w,height:h,fill:'none',stroke:c,'stroke-width':stroke}));badge(g,x,y,c,label);}
    if(m.type==='strikeout'&&!m.rects){g.append(el('line',{x1:x,y1:y+h/2,x2:x+w,y2:y+h/2,stroke:c,'stroke-width':stroke,'stroke-linecap':'round'}));badge(g,x,y+h/2-14,c,label);}
    if(m.type==='freehand'){
      const points=m.points||[];
      g.append(el('polyline',{points:points.map(p=>`${p[0]*viewW},${p[1]*viewH}`).join(' '),stroke:c,'stroke-width':stroke,'stroke-linecap':'round','stroke-linejoin':'round',fill:'none'}));
      if(points.length)badge(g,points[0][0]*viewW,points[0][1]*viewH-14,c,label);
    }
    if(m.type==='freetext'&&m.id!==inlineId){
      const text=el('text',{x,y:y+m.size,fill:c,'font-size':m.size,'font-family':'sans-serif',opacity:m.text?1:0.45});
      (m.text||'글씨를 입력하세요').split('\n').forEach((line,i)=>text.append(el('tspan',{x,dy:i?'1.35em':0},line)));g.append(text);
    }
    g.append(el('title',{},m.text||labels[m.type]));svg.append(g);return g;
  }
  // 번호 동그라미 자리(보기 좌표). 여백의 설명 말풍선·입력칸이 이 높이에 놓이고 점선이 여기서 시작합니다.
  function anchorOf(m){
    const x=m.x*viewW,y=m.y*viewH,h=m.h*viewH,clamp=(a,b)=>[Math.max(10,a),Math.max(10,b)];
    if(m.type==='point')return [x,y];
    if(m.rects&&(m.type==='highlight'||m.type==='strikeout'))return clamp(m.rects[0][0]*viewW,m.rects[0][1]*viewH);
    if(m.type==='highlight'||m.type==='area')return clamp(x,y);
    if(m.type==='strikeout')return clamp(x,y+h/2-14);
    if(m.type==='freehand'&&(m.points||[]).length)return clamp(m.points[0][0]*viewW,m.points[0][1]*viewH-14);
    return null;
  }
  // 여백에 놓을 것: 설명이 있는 표시의 말풍선 + 지금 쓰는 입력칸(글씨 도구는 문서에 직접 쓰므로 제외).
  function buildMargin(){
    for(const child of [...margin.children])if(child!==commentBox)child.remove();
    placed=[];
    for(const m of onPage()){
      if(m.type==='freetext')continue;
      const editing=m.id===commentId&&commentBox;
      if(!editing&&!(m.text||'').trim())continue;
      const at=anchorOf(m);if(!at)continue;
      let node=commentBox;
      if(!editing){
        node=document.createElement('div');node.className='ann-bubble'+(m.id===active?' is-active':'');node.dataset.id=m.id;node.textContent=m.text;
        node.addEventListener('pointerenter',()=>setActive(m.id));
        node.addEventListener('click',()=>{if(data.editable)openComment(m);else setActive(m.id);});
        margin.append(node);
      }
      node.style.setProperty('--mark',m.color);
      placed.push({m,at,node});
    }
    placed.sort((a,b)=>a.at[1]-b.at[1]||a.at[0]-b.at[0]);
    placeMargin();
  }
  // 높이를 번호에 맞추고(겹치면 아래로), 번호 → 문서 오른쪽 끝 → 말풍선 왼쪽 가운데로 점선을 긋습니다.
  function placeMargin(){
    const scale=paper.clientWidth/viewW;let floor=0;
    for(const item of placed){
      const top=Math.max(item.at[1]*scale-14,floor);
      item.node.style.top=`${top}px`;item.top=top;floor=top+item.node.offsetHeight+8;
    }
    margin.style.minHeight=`${Math.max(paper.clientHeight,floor)}px`;
    const width=stage.scrollWidth,height=Math.max(stage.scrollHeight,floor);
    links.setAttribute('width',width);links.setAttribute('height',height);links.setAttribute('viewBox',`0 0 ${width} ${height}`);
    links.replaceChildren(...placed.map(item=>{
      const x=paper.offsetLeft+item.at[0]*scale,y=paper.offsetTop+item.at[1]*scale,edge=paper.offsetLeft+paper.clientWidth,to=margin.offsetLeft,ty=item.top+14;
      return el('polyline',{points:`${x},${y} ${edge+6},${y} ${to},${ty}`,stroke:item.m.color,class:'ann-link'+(item.m.id===active?' is-active':''),'data-id':item.m.id});
    }));
  }
  function drawMarks(){
    svg.replaceChildren();
    onPage().forEach((m,i)=>showMark(m,i));
    if(draft)showMark(draft,onPage().length).id='ann-draft';
    buildMargin();
  }
  function setActive(id,scroll=false){
    active=id;
    svg.querySelectorAll('.ann-mark').forEach(g=>g.classList.toggle('is-active',g.dataset.annotationId===id));
    list.querySelectorAll('.ann-note').forEach(n=>n.classList.toggle('is-active',n.dataset.id===id));
    margin.querySelectorAll('.ann-bubble').forEach(b=>b.classList.toggle('is-active',b.dataset.id===id));
    links.querySelectorAll('.ann-link').forEach(l=>l.classList.toggle('is-active',l.dataset.id===id));
    if(scroll)svg.querySelector(`[data-annotation-id="${CSS.escape(id)}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  const grow=area=>{area.style.height='auto';area.style.height=`${area.scrollHeight+2}px`;};
  function card(m,i){
    const note=document.createElement('article');note.className='ann-note'+(m.id===active?' is-active':'');note.dataset.id=m.id;
    const head=document.createElement('div');head.className='ann-note-head';
    const num=document.createElement('span');num.className='ann-note-num';num.style.setProperty('--mark',m.color);num.style.color=ink(m.color);num.textContent=String(i+1);
    // 운영팀 11/17: 목록 이름은 '형광펜'·'취소선' 같은 도구 이름 대신 문서의 표시와 같은 번호(①②③)만 보여 줍니다. 도구 이름은 마우스를 올리면 보입니다.
    num.title=labels[m.type]||m.type;num.setAttribute('aria-label',`${i+1}번 첨삭`);head.append(num);note.append(head);
    if(m.quote){const quote=document.createElement('q');quote.className='ann-quote';quote.textContent=m.quote.length>140?m.quote.slice(0,140)+'…':m.quote;note.append(quote);}
    if(data.editable){
      const del=document.createElement('button');del.type='button';del.className='ann-icon-btn ann-note-delete';del.title='이 첨삭 삭제';del.setAttribute('aria-label',`${i+1}번 첨삭 삭제`);
      del.innerHTML='<svg class="et-icon" aria-hidden="true"><use href="#i-trash"/></svg>';
      del.addEventListener('click',()=>{remember();marks=marks.filter(a=>a.id!==m.id);if(active===m.id)active=null;render();setStatus(pendingText);});
      head.append(del);
      const area=document.createElement('textarea');area.rows=2;area.maxLength=2000;area.value=m.text||'';
      area.placeholder=m.type==='freetext'?'문서에 쓸 글씨를 입력하세요':'설명을 적으세요 (비워 두어도 됩니다)';
      area.setAttribute('aria-label',`${i+1}번 첨삭 설명`);
      let recorded=false;
      area.addEventListener('focus',()=>{recorded=false;setActive(m.id);});
      area.addEventListener('input',()=>{
        if(!recorded){remember();recorded=true;}
        const target=marks.find(a=>a.id===m.id);if(target)target.text=area.value;
        grow(area);drawMarks();setStatus(pendingText);
      });
      note.append(area);requestAnimationFrame(()=>grow(area));
    } else {
      const text=document.createElement('p');text.textContent=m.text||'(설명 없음)';note.append(text);
    }
    note.addEventListener('pointerenter',()=>setActive(m.id));
    note.addEventListener('click',event=>{if(!event.target.closest('button,textarea'))setActive(m.id,true);});
    return note;
  }
  function render(){
    drawMarks();
    const visible=onPage(),others=marks.length-visible.length;
    list.replaceChildren(...visible.map(card));
    if(!visible.length){const p=document.createElement('p');p.className='lms-muted ann-empty';p.textContent='이 쪽에는 첨삭이 없습니다.';list.append(p);}
    if(count)count.textContent=`${visible.length}개${others?` · 다른 쪽 ${others}개`:''}`;
  }
  function loadWords(){
    words=[];
    if(!data.editable||!data.wordsUrl)return;
    const wanted=page;
    fetch(data.wordsUrl.replace('{page}',String(page)),{credentials:'same-origin'}).then(r=>r.ok?r.json():{words:[]}).then(result=>{
      if(wanted!==page)return;
      words=Array.isArray(result.words)?result.words:[];
      if(words.length&&!dirty)setStatus('이 쪽은 글자를 인식했습니다. 형광펜·취소선은 글자를 드래그하면 그 글자에만 그어집니다.');
    }).catch(()=>{words=[];});
  }
  function loadPage(){
    if(inlineBox)closeInlineText();
    if(commentBox)closeComment();
    draft=null;drawStart=null;textPick=null;loadWords();
    $('ann-page-label').textContent=`${page} / ${data.pageCount}쪽`;
    $('ann-prev').disabled=page===1;$('ann-next').disabled=page===data.pageCount;
    image.onload=()=>{viewW=1000;viewH=viewW*image.naturalHeight/image.naturalWidth;svg.setAttribute('viewBox',`0 0 ${viewW} ${viewH}`);render();if(!dirty)setStatus(data.editable?(words.length?'이 쪽은 글자를 인식했습니다. 형광펜·취소선은 글자를 드래그하면 그 글자에만 그어집니다.':'도구를 고르고 문서를 누르거나 드래그하세요.'):'저장된 첨삭입니다. 첨삭 카드를 누르면 문서의 해당 위치를 보여 줍니다.');};
    image.onerror=()=>setStatus('페이지를 불러오지 못했습니다. 연결·로그인 상태를 확인한 뒤 다시 열어 주세요.',true);
    image.src=data.imageUrl.replace('{page}',String(page));
  }
  $('ann-prev').addEventListener('click',()=>{if(page>1){page--;loadPage();}});
  $('ann-next').addEventListener('click',()=>{if(page<data.pageCount){page++;loadPage();}});
  // 문서 폭 = 보이는 칸 - 여백(좁은 화면은 여백을 줄임). 확대하면 옆으로 넘쳐 스크롤됩니다.
  const scroller=stage.parentElement;
  const fit=()=>{
    const room=scroller.clientWidth-32,side=room>=760?240:170;stage.style.setProperty('--ann-margin',`${side}px`);
    const base=Math.min(840,Math.max(200,room-side-28));paper.style.width=`${base*Number($('ann-zoom').value)}px`;
  };
  $('ann-zoom').addEventListener('change',fit);
  new ResizeObserver(fit).observe(scroller);fit();
  new ResizeObserver(()=>placeMargin()).observe(paper);
  if(!data.editable){svg.classList.add('readonly');loadPage();return;}

  // 의견 제출이 막혀 다시 그려진 화면이면, 보내기 직전에 남겨 둔 첨삭을 되살립니다(그사이 다른 저장이 있었으면 버림).
  try{
    const saved=JSON.parse(sessionStorage.getItem(draftKey)||'null');sessionStorage.removeItem(draftKey);
    if(saved&&saved.base===revision&&Array.isArray(saved.marks)){marks=saved.marks;dirty=true;changeNo++;}
  }catch(_){}

  const press=(selector,key,value)=>root.querySelectorAll(selector).forEach(b=>b.setAttribute('aria-pressed',String(b.dataset[key]===String(value))));
  root.querySelectorAll('.ann-tool').forEach(b=>b.addEventListener('click',()=>{tool=b.dataset.tool;press('.ann-tool','tool',tool);paper.dataset.tool=tool;}));
  root.querySelectorAll('.ann-swatch').forEach(b=>b.addEventListener('click',()=>{color=b.dataset.color;press('.ann-swatch','color',color);}));
  root.querySelectorAll('.ann-width').forEach(b=>b.addEventListener('click',()=>{width=Number(b.dataset.width);size=Number(b.dataset.size);press('.ann-width','width',width);}));
  paper.dataset.tool=tool;

  function point(event){const r=svg.getBoundingClientRect();return [Math.min(1,Math.max(0,(event.clientX-r.left)/r.width)),Math.min(1,Math.max(0,(event.clientY-r.top)/r.height))];}
  // '글씨' 도구: 누른 자리에 바로 입력 칸을 띄워 문서 위에 직접 씁니다. Enter·바깥 누르기로 마치고, 비워 두면 지웁니다.
  function closeInlineText(){
    if(!inlineBox)return;
    const box=inlineBox,mark=marks.find(m=>m.id===inlineId);inlineBox=null;inlineId=null;box.remove();
    if(mark&&!mark.text.trim()){marks=marks.filter(m=>m.id!==mark.id);if(active===mark.id)active=null;}
    render();
  }
  function openInlineText(mark){
    closeInlineText();
    const box=document.createElement('textarea'),scale=paper.getBoundingClientRect().width/viewW;
    box.className='ann-inline-text';box.rows=1;box.value=mark.text||'';box.setAttribute('aria-label','문서에 쓸 글씨');box.placeholder='글씨 입력';
    Object.assign(box.style,{left:`${mark.x*100}%`,top:`${mark.y*100}%`,color:mark.color,fontSize:`${Math.max(12,mark.size*scale)}px`});
    inlineBox=box;inlineId=mark.id;paper.append(box);setActive(mark.id);drawMarks();
    let recorded=false;
    const grow=()=>{box.style.height='auto';box.style.height=`${box.scrollHeight}px`;};
    box.addEventListener('input',()=>{
      if(!recorded){remember();recorded=true;}
      const target=marks.find(m=>m.id===mark.id);if(target)target.text=box.value;
      const area=list.querySelector(`[data-id="${CSS.escape(mark.id)}"] textarea`);if(area)area.value=box.value;
      grow();setStatus(pendingText);
    });
    box.addEventListener('keydown',event=>{if(event.key==='Escape'||(event.key==='Enter'&&!event.shiftKey&&!event.isComposing)){event.preventDefault();closeInlineText();}});
    box.addEventListener('blur',()=>setTimeout(()=>{if(inlineBox===box)closeInlineText();},0));
    grow();box.focus({preventScroll:true});
  }
  // 표시를 만들면 여백(번호와 같은 높이)에 설명 입력칸이 뜹니다. Enter·바깥 누르기로 마치고, 비워 두어도 표시는 남습니다.
  function closeComment(){
    if(!commentBox)return;
    const box=commentBox;commentBox=null;commentId=null;box.remove();drawMarks();
  }
  function openComment(mark){
    closeInlineText();closeComment();
    if(!anchorOf(mark))return;
    const box=document.createElement('textarea');
    box.className='ann-inline-comment';box.rows=1;box.maxLength=2000;box.value=mark.text||'';box.placeholder='설명 입력 · Enter로 마침';
    box.setAttribute('aria-label',`${onPage().findIndex(m=>m.id===mark.id)+1}번 첨삭 설명`);
    commentBox=box;commentId=mark.id;margin.append(box);setActive(mark.id);drawMarks();
    let recorded=false;
    const resize=()=>{box.style.height='auto';box.style.height=`${box.scrollHeight+2}px`;placeMargin();};
    box.addEventListener('input',()=>{
      if(!recorded){remember();recorded=true;}
      const target=marks.find(m=>m.id===mark.id);if(target)target.text=box.value;
      const area=list.querySelector(`[data-id="${CSS.escape(mark.id)}"] textarea`);if(area){area.value=box.value;grow(area);}
      resize();setStatus(pendingText);
    });
    box.addEventListener('keydown',event=>{if(event.key==='Escape'||(event.key==='Enter'&&!event.shiftKey&&!event.isComposing)){event.preventDefault();closeComment();}});
    box.addEventListener('blur',()=>setTimeout(()=>{if(commentBox===box)closeComment();},0));
    resize();box.focus({preventScroll:true});
  }
  svg.addEventListener('pointerdown',event=>{
    if(event.button!==0||!image.complete||!image.naturalWidth)return;
    if(inlineBox)closeInlineText();
    if(commentBox)closeComment();
    // 글씨 도구로 이미 쓴 글씨를 누르면 그 글씨를 다시 고칩니다.
    const existing=tool==='freetext'?marks.find(m=>m.type==='freetext'&&m.id===event.target.closest('.ann-mark')?.dataset.annotationId):null;
    if(existing){event.preventDefault();openInlineText(existing);return;}
    event.preventDefault();drawStart=point(event);try{svg.setPointerCapture(event.pointerId);}catch(_){}
    draft={id:newId(),page,type:tool,x:drawStart[0],y:drawStart[1],w:0,h:0,points:[drawStart],text:'',color,size,width};
    // 형광펜·취소선을 글자 위에서 시작하면 글자 단위로 고릅니다(글자 층이 없거나 빈 곳이면 기존처럼 상자로).
    const start=TEXT_TOOLS.has(tool)&&words.length?wordAt(drawStart):-1;
    textPick=start>=0?{start,end:start}:null;
    if(textPick){applyPick(draft);svg.querySelector('#ann-draft')?.remove();showMark(draft,onPage().length).id='ann-draft';}
  });
  svg.addEventListener('pointermove',event=>{
    if(!draft){svg.style.cursor=TEXT_TOOLS.has(tool)&&words.length&&wordAt(point(event))>=0?'text':'';return;}
    if(!drawStart)return;const p=point(event);
    if(textPick){
      const at=nearestWord(p);if(at>=0&&at!==textPick.end){textPick.end=at;applyPick(draft);}
      svg.querySelector('#ann-draft')?.remove();showMark(draft,onPage().length).id='ann-draft';return;
    }
    if(draft.type==='freehand'){if(draft.points.length<2900)draft.points.push(p);}
    else {draft.x=Math.min(drawStart[0],p[0]);draft.y=Math.min(drawStart[1],p[1]);draft.w=Math.abs(p[0]-drawStart[0]);draft.h=Math.abs(p[1]-drawStart[1]);}
    svg.querySelector('#ann-draft')?.remove();
    showMark(draft,onPage().length).id='ann-draft';
  });
  svg.addEventListener('pointerup',event=>{
    if(!draft)return;
    if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);
    const p=point(event),mark=draft,picked=textPick,from=drawStart;draft=null;drawStart=null;textPick=null;
    // 글자 고르기는 실제로 끌었을 때만(누르기만 한 실수 클릭으로 표시가 생기지 않게).
    if(picked&&Math.hypot(p[0]-from[0],p[1]-from[1])<0.004){render();return;}
    if(picked){mark.points=[];}
    else if(mark.type==='point'||mark.type==='freetext'){mark.x=p[0];mark.y=p[1];mark.w=0;mark.h=0;mark.points=[];}
    else if(mark.type==='freehand'){mark.points.push(p);mark.x=0;mark.y=0;mark.w=0;mark.h=0;if(mark.points.length<2){render();return;}}
    else {mark.points=[];if(mark.w<.002){render();return;}if(mark.h<.002)mark.h=Math.min(.01,1-mark.y);}
    remember();marks.push(mark);active=mark.id;render();setStatus(pendingText);
    if(mark.type==='freetext'){openInlineText(mark);return;}
    openComment(mark);
  });
  svg.addEventListener('pointercancel',()=>{draft=null;drawStart=null;textPick=null;render();});
  $('ann-undo').addEventListener('click',()=>{if(history.length){marks=history.pop();dirty=true;changeNo++;render();setStatus('실행을 취소했습니다. '+pendingText);}});

  if(data.mode==='review'&&form){
    form.addEventListener('submit',()=>{
      const fields=form.querySelectorAll('[name=document],[name=document_revision],[name=annotations]');
      if(!dirty){fields.forEach(f=>{f.disabled=true;});}
      else {
        form.querySelector('[name=annotations]').value=JSON.stringify(marks);
        try{sessionStorage.setItem(draftKey,JSON.stringify({base:revision,marks}));}catch(_){}
      }
      dirty=false;
    });
  }
  $('ann-save')?.addEventListener('click',async()=>{
    if(saving)return;saving=true;const button=$('ann-save');button.disabled=true;
    const sentChange=changeNo;setStatus('첨삭을 저장하는 중입니다…');
    try{
      const response=await fetch(data.saveUrl,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({revision,annotations:marks})});
      const result=await response.json().catch(()=>({error:'로그인 또는 서버 응답을 확인하세요.'}));
      if(!response.ok)throw new Error(result.error||'저장 실패');
      revision=result.revision;if(changeNo===sentChange)dirty=false;
      setStatus(dirty?'앞선 첨삭은 저장되었습니다. 이후 변경사항은 한 번 더 저장하세요.':'첨삭을 저장했습니다. 학생·연결 학부모가 확인할 수 있습니다.');
    }catch(error){setStatus(error.message+' 현재 화면의 첨삭은 그대로 유지됩니다.',true);}
    finally{saving=false;button.disabled=false;}
  });
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  if(dirty)setStatus('보내지 못한 첨삭을 다시 불러왔습니다. 확인 후 의견 제출을 눌러 주세요.');
  loadPage();
})();
