import json
from pathlib import Path
from urllib.parse import quote
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import F
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render,redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST,require_http_methods
from apps.assignments.models import Submission
from apps.learning.models import QuizAttempt
from .access import require_submission,require_attempt
from .documents import create_preview,render_page,document_is_current,clean_annotations,page_words,PreviewError,ANNOTATION_TOOLS,ANNOTATION_COLOR_NAMES,ANNOTATION_WIDTH_NAMES
from .forms import validate_file
from .models import ReviewDocument,SubmissionFile
from .room_views import audit


def page_url_pattern(name,pk):
    """'{page}' 자리표시가 든 주소(첨삭 화면 JS가 쪽 번호로 바꿈). 11/24: 문서 번호가 1이면 '/1/'을 두 번 바꿔 글자 맞춤이 깨지던 것 수정."""
    sentinel=987654321
    return reverse(name,args=[pk,sentinel]).replace(str(sentinel),'{page}')


def annotator_data(doc,*,editable,mode):
    """첨삭 화면(annotation.js)에 넘기는 값. mode='review'는 '의견 제출'로, 'document'는 첨삭 저장 버튼으로 저장합니다."""
    return {'documentId':doc.pk,'annotations':doc.annotations,'revision':doc.revision,'pageCount':doc.page_count,
      'editable':editable,'mode':mode,'imageUrl':reverse('lms:document-page',args=[doc.pk,1]).replace('/1.png','/{page}.png'),
      'saveUrl':reverse('lms:document-annotations',args=[doc.pk]),
      'wordsUrl':page_url_pattern('lms:document-words',doc.pk),
      'tools':[{'id':i,'label':label,'icon':icon,'hint':hint} for i,label,icon,hint in ANNOTATION_TOOLS],
      'colors':[{'hex':hexval,'label':label} for hexval,label in ANNOTATION_COLOR_NAMES],
      'widths':[{'width':width,'label':label,'size':size} for width,label,size in ANNOTATION_WIDTH_NAMES]}


def resolve_doc(request,pk,write=False):
    doc=get_object_or_404(ReviewDocument.objects.select_related('submission__recipient__assignment','attempt__recipient__quiz'),pk=pk)
    staff=require_submission(request.user,doc.submission,write) if doc.submission_id else require_attempt(request.user,doc.attempt,write)
    return doc,staff


@login_required
@require_POST
def prepare_submission(request,submission_id):
    submission=get_object_or_404(Submission.objects.select_related('recipient__assignment'),pk=submission_id)
    require_submission(request.user,submission,write=True)
    source=request.POST.get('source','primary')
    upload=request.FILES.get('preview')
    try:
        if upload:
            validate_file(upload)
            if Path(upload.name).suffix.lower()!='.pdf':raise ValidationError('첨삭 미리보기는 PDF만 등록하세요.')
        doc=create_preview(user=request.user,submission=submission,source=source,preview=upload)
    except (PreviewError,ValidationError) as exc:
        return render(request,'lms/preview_error.html',{'page_title':'첨삭 미리보기 준비','error':str(exc),
          'submission':submission,'source':source},status=422)
    if request.POST.get('return')=='review':
        return redirect(reverse('lms:submission-review',args=[submission.pk])+'?file='+quote(source))
    return redirect('lms:document',doc.pk)


@login_required
@require_POST
def prepare_quiz(request,attempt_id):
    attempt=get_object_or_404(QuizAttempt.objects.select_related('recipient__quiz'),pk=attempt_id)
    require_attempt(request.user,attempt,write=True)
    try:doc=create_preview(user=request.user,attempt=attempt)
    except PreviewError as exc:
        messages.error(request,str(exc));return redirect('lms:quiz-review',attempt.pk)
    return redirect('lms:document',doc.pk)


@login_required
def document(request,document_id):
    doc,staff=resolve_doc(request,document_id)
    current=document_is_current(doc)
    back=reverse('lms:submission-review',args=[doc.submission_id]) if doc.submission_id else reverse('lms:quiz-review',args=[doc.attempt_id])
    return render(request,'lms/document.html',{'page_title':'파일 첨삭','doc':doc,'editable':staff and current,
      'current':current,'back':back,'document_data':annotator_data(doc,editable=staff and current,mode='document')})


@login_required
def document_page(request,document_id,page):
    doc,_=resolve_doc(request,document_id)
    try:data=render_page(doc,page)
    except PreviewError as exc:return HttpResponse(str(exc),status=422,content_type='text/plain; charset=utf-8')
    response=HttpResponse(data,content_type='image/png');response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff';return response


@login_required
def document_words(request,document_id,page):
    """그 쪽 단어 위치(글자 드래그 형광펜·취소선용). 글자 층이 없으면 빈 목록."""
    doc,_=resolve_doc(request,document_id)
    response=JsonResponse({'words':page_words(doc,page)});response['Cache-Control']='private, no-store'
    return response


@login_required
@require_POST
def document_annotations(request,document_id):
    doc,_=resolve_doc(request,document_id,write=True)
    if not document_is_current(doc):return JsonResponse({'error':'재제출 전 파일입니다. 기존 첨삭은 읽기 전용으로 보존됩니다.'},status=409)
    if len(request.body)>800_000:return JsonResponse({'error':'첨삭 데이터가 너무 큽니다.'},status=413)
    try:
        payload=json.loads(request.body)
        if not isinstance(payload,dict) or type(payload.get('revision')) is not int:raise ValueError
        clean=clean_annotations(payload.get('annotations'),doc.page_count)
    except (ValueError,TypeError,ValidationError) as exc:
        return JsonResponse({'error':'첨삭 입력을 확인하세요. '+str(exc)[:300]},status=400)
    with transaction.atomic():
        # Lock parent as well: a re-submission must not race with saving annotations.
        if doc.submission_id:Submission.objects.select_for_update().get(pk=doc.submission_id)
        locked=ReviewDocument.objects.select_for_update().select_related('submission__recipient__assignment','attempt__recipient__quiz').get(pk=doc.pk)
        if not document_is_current(locked):return JsonResponse({'error':'학생 재제출이 먼저 저장되었습니다. 새 제출물을 열어 주세요.'},status=409)
        changed=ReviewDocument.objects.filter(pk=doc.pk,revision=payload['revision']).update(
          annotations=clean,revision=F('revision')+1,updated_by=request.user,updated_at=timezone.now())
        if not changed:return JsonResponse({'error':'다른 사용자가 먼저 첨삭을 저장했습니다. 새로고침 전 입력 내용을 보관해 주세요.'},status=409)
        audit(request.user,'annotation.save',doc.pk,revision=payload['revision']+1,count=len(clean))
    return JsonResponse({'ok':True,'revision':payload['revision']+1})


@login_required
def submission_file(request,file_id):
    from django.http import FileResponse
    f=get_object_or_404(SubmissionFile.objects.select_related('submission__recipient__assignment'),pk=file_id)
    require_submission(request.user,f.submission)
    response=FileResponse(f.file.open('rb'),as_attachment=True,filename=f.original_name)
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


def _discussion_file_permission(user,discussion):
    from .access import can_manage
    from apps.operations.access import learner_student_ids
    if can_manage(user,discussion):return
    if discussion.is_available and discussion.recipients.filter(student_id__in=learner_student_ids(user)).exists():return
    raise Http404('접근 가능한 토론 파일이 아닙니다.')

@login_required
def discussion_attachment(request,discussion_id):
    from apps.learning.models import Discussion
    from django.http import FileResponse
    obj=get_object_or_404(Discussion,pk=discussion_id)
    _discussion_file_permission(request.user,obj)
    if not obj.attachment:raise Http404
    response=FileResponse(obj.attachment.open('rb'),as_attachment=True,filename=Path(obj.attachment.name).name)
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff';return response

@login_required
def discussion_comment_attachment(request,comment_id):
    from apps.learning.models import DiscussionComment
    from django.http import FileResponse
    obj=get_object_or_404(DiscussionComment.objects.select_related('discussion'),pk=comment_id)
    _discussion_file_permission(request.user,obj.discussion)
    if not obj.attachment:raise Http404
    response=FileResponse(obj.attachment.open('rb'),as_attachment=True,filename=Path(obj.attachment.name).name)
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff';return response
