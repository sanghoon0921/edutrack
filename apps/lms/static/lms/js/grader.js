/* 채점 화면: 학생 목록에서 고르면 그 학생으로 이동, PDF·이미지·텍스트처럼 바로 열 수 있는 파일은 화면을 열 때 첨삭 문서로 바꿉니다. */
(() => {
  'use strict';
  document.querySelector('[data-grader-jump]')?.addEventListener('change',event=>{if(event.target.value)location.href=event.target.value;});
  const open=document.querySelector('form[data-grader-open]');
  if(open){open.querySelector('button').disabled=true;open.submit();}
})();
