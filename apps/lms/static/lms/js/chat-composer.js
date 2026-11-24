/* One physical Enter => one submit, including Korean IME commit. Shift+Enter => newline. */
(() => {
  'use strict';
  if (window.EduChatComposer) return;
  function bind(form, area) {
    if (!form || !area || area.dataset.enterBound) return;
    area.dataset.enterBound = 'true';
    let composing=false, pending=null, timer=null, held=false, sent=false, endedAt=0;
    function submit() {
      if (sent) return;
      sent=true; pending=null;
      if (!area.value.trim() || form.querySelector('button[type="submit"]')?.disabled) return;
      form.requestSubmit();
    }
    function flush() {
      clearTimeout(timer);
      timer=setTimeout(()=>{ if(!composing && pending==='send') submit(); },0);
    }
    area.addEventListener('compositionstart',()=>{composing=true;pending=null;sent=false;});
    area.addEventListener('compositionend',()=>{composing=false;endedAt=performance.now();if(pending==='send')flush();});
    area.addEventListener('keydown',event=>{
      if(event.key!=='Enter') {if(!event.isComposing)held=false;return;}
      if(event.repeat || held){event.preventDefault();return;}
      held=true;sent=false;
      if(event.shiftKey){pending=null;return;}
      if(composing || event.isComposing || event.keyCode===229){
        // Let the IME finalize the syllable first; submit after its final input event.
        pending='send'; if(!composing)flush(); return;
      }
      event.preventDefault();pending='send';flush();
    });
    area.addEventListener('keyup',event=>{
      if(event.key!=='Enter')return;
      if(!event.shiftKey && !held && !sent && performance.now()-endedAt<120){pending='send';flush();}
      held=false;
      // Do not cancel a pending commit/submit until the queued input events settle.
    });
    area.addEventListener('blur',()=>{held=false;});
  }
  window.EduChatComposer={bind};
})();
