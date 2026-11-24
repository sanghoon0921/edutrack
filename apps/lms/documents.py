"""Document versions, bounded previews and normalized annotation validation."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError
from django.http import Http404

from .models import ReviewDocument


class PreviewError(Exception): pass


def run_worker(mode,source,output,**kwargs):
    cmd=[sys.executable,str(Path(__file__).with_name('document_worker.py')),mode,str(source),str(output)]
    for key,value in kwargs.items():cmd += ['--'+key,str(value)]
    try:
        result=subprocess.run(cmd,capture_output=True,timeout=65,shell=False)
    except subprocess.TimeoutExpired as exc:
        raise PreviewError('미리보기 생성 시간이 초과되었습니다. 더 작은 PDF 또는 직접 저장한 PDF를 등록하세요.') from exc
    if result.returncode or not Path(output).is_file():
        error='문서를 열지 못했습니다. 암호·손상 여부와 미리보기 모듈 설치 상태를 확인하세요.'
        for line in result.stderr.decode('utf-8',errors='replace').splitlines():
            try:error=json.loads(line)['error']
            except (ValueError,KeyError,TypeError):continue
        raise PreviewError(error)
    return Path(output)


def version_token(submission):
    return hashlib.sha256(f'{submission.pk}|{submission.submitted_at}|{submission.attachment.name if submission.attachment else ""}|{submission.text_answer}'.encode()).hexdigest()


def attempt_token(attempt):
    return hashlib.sha256(f'quiz|{attempt.pk}|{attempt.submitted_at}'.encode()).hexdigest()


def get_source(submission, source):
    if source=='text':
        if not submission.text_answer.strip():raise Http404('텍스트 답안이 없습니다.')
        return 'text','텍스트 답안.txt',None,submission.text_answer
    if source=='primary':
        if not submission.attachment:raise Http404('제출 파일이 없습니다.')
        return submission.attachment.name,submission.attachment_name or Path(submission.attachment.name).name,submission.attachment,None
    try:
        f=submission.extra_files.get(pk=int(source))
    except (ValueError,TypeError,submission.extra_files.model.DoesNotExist):
        raise Http404('제출 파일이 없습니다.')
    return f.file.name,f.original_name,f.file,None


def quiz_text(attempt):
    lines=[attempt.recipient.quiz.title, f'학생: {attempt.recipient.student_name} · {attempt.attempt_no}회 응시','', '학생이 제출한 답안입니다.']
    from apps.learning import quiz_types
    for answer in attempt.answers.select_related('question','selected_choice').prefetch_related('question__choices').order_by('question__order','pk'):
        lines += ['',f'{answer.question.order}. {quiz_types.display_prompt(answer.question)}',
          '학생 답안: '+quiz_types.answer_text(answer.question,quiz_types.response_for(answer))]
    return '\n'.join(lines)


def create_preview(*,user,submission=None,attempt=None,source='primary',preview=None):
    if submission:
        key,name,file,text=get_source(submission,source);token=version_token(submission)
        query={'submission':submission,'source_key':key,'source_token':token}
    else:
        key,name,file,text='answers','퀴즈 답안.txt',None,quiz_text(attempt)
        token=attempt_token(attempt);query={'attempt':attempt,'source_key':key,'source_token':token}
    existing=ReviewDocument.objects.filter(**query).first()
    if existing:
        if preview:raise PreviewError('이미 미리보기와 첨삭이 있는 파일입니다. 기존 미리보기를 덮어쓰지 않습니다.')
        return existing
    with tempfile.TemporaryDirectory(prefix='edutrack-preview-') as td:
        td=Path(td);out=td/'preview.pdf'
        if preview:
            original=td/'input.pdf'
            with original.open('wb') as dest:
                for chunk in preview.chunks():dest.write(chunk)
            run_worker('convert',original,out)
        elif text is not None:
            original=td/'input.txt';original.write_text(text,encoding='utf-8');run_worker('text',original,out)
        else:
            original=td/('input'+Path(name).suffix.lower())
            with file.open('rb') as src,original.open('wb') as dest:
                total=0
                while chunk:=src.read(1024*1024):
                    total+=len(chunk)
                    if total>30*1024*1024:raise PreviewError('미리보기 원본은 30MB 이하로 제한됩니다.')
                    dest.write(chunk)
            run_worker('convert',original,out,converter=getattr(settings,'LMS_OFFICE_CONVERTER',''))
        info=td/'info.json';run_worker('info',out,info)
        pages=json.loads(info.read_text())['pages']
        # 텍스트 답안은 그릴 때 남긴 단어 위치를 그대로 씁니다. PDF 는 쪽을 처음 볼 때 page_words 가 채웁니다.
        sidecar=Path(str(out)+'.words.json')
        layer=json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.is_file() else None
        doc=ReviewDocument(**query,original_name=name,page_count=pages,updated_by=user,text_layer=layer)
        doc.pdf.save('preview.pdf',ContentFile(out.read_bytes()),save=False)
        try:
            with transaction.atomic():doc.save()
        except IntegrityError:
            doc.pdf.storage.delete(doc.pdf.name)
            doc=ReviewDocument.objects.get(**query)
        return doc


def document_is_current(doc):
    if doc.submission_id:
        sub=doc.submission
        active_keys={sub.attachment.name if sub.attachment else '', 'text'}|set(sub.extra_files.values_list('file',flat=True))
        return doc.source_token==version_token(sub) and doc.source_key in active_keys
    return doc.source_token==attempt_token(doc.attempt)


def render_page(doc,page):
    if not 1<=page<=doc.page_count:raise Http404('페이지가 없습니다.')
    with tempfile.TemporaryDirectory(prefix='edutrack-render-') as td:
        td=Path(td);source=td/'source.pdf'
        with doc.pdf.open('rb') as file:source.write_bytes(file.read(31*1024*1024))
        out=td/'page.png';run_worker('render',source,out,page=page)
        return out.read_bytes()


# 첨삭 화면 도구 막대와 저장 검증이 같은 목록을 씁니다.
ANNOTATION_TOOLS=(('point','지점','pin','원하는 위치에 번호를 찍고 설명'),('highlight','형광펜','highlighter','드래그한 곳을 형광펜으로 칠하고 설명'),
  ('freetext','글씨','type','누른 위치에 글씨를 바로 쓰기'),('strikeout','취소선','strike','드래그한 곳에 취소선을 긋고 설명'),
  ('freehand','손그림','pen','손으로 그리고 설명'),('area','영역','square-dashed','드래그한 구역을 상자로 묶고 설명'))
ANNOTATION_COLOR_NAMES=(('#dc2626','빨강'),('#ea580c','주황'),('#eab308','노랑'),('#16a34a','초록'),('#2563eb','파랑'),('#7c3aed','보라'),('#111827','검정'))
ANNOTATION_COLORS=tuple(color for color,_ in ANNOTATION_COLOR_NAMES)
# 선 굵기 3단계(가늘게·보통·굵게)와 그때의 글씨 크기. 굵기 정보가 없는 예전 첨삭은 보통으로 그립니다.
ANNOTATION_WIDTH_NAMES=((2,'가늘게',16),(4,'보통',20),(7,'굵게',28))
ANNOTATION_WIDTHS=tuple(width for width,_,_ in ANNOTATION_WIDTH_NAMES)


def page_words(doc,page):
    """그 쪽의 단어 위치 목록(글자 드래그 형광펜·취소선용). 처음 한 번만 PDF 에서 읽고 doc.text_layer 에 남깁니다.
    스캔·이미지처럼 글자 층이 없거나 읽기에 실패하면 빈 목록(이때는 상자로 긋는 기존 방식)."""
    if not 1<=page<=doc.page_count:raise Http404('페이지가 없습니다.')
    layer=doc.text_layer or {}
    if str(page) in layer:return layer[str(page)]
    words=[]
    with tempfile.TemporaryDirectory(prefix='edutrack-words-') as td:
        td=Path(td);source=td/'source.pdf'
        with doc.pdf.open('rb') as file:source.write_bytes(file.read(31*1024*1024))
        try:words=json.loads(run_worker('words',source,td/'words.json',page=page).read_text(encoding='utf-8'))['words']
        except (PreviewError,ValueError,KeyError):words=[]
    layer={**layer,str(page):words}
    ReviewDocument.objects.filter(pk=doc.pk).update(text_layer=layer);doc.text_layer=layer
    return words


TEXT_MARK_TYPES={'highlight','strikeout'}


def clean_annotations(raw,page_count):
    if not isinstance(raw,list) or len(raw)>600:raise ValidationError('첨삭은 문서당 최대 600개입니다.')
    allowed_types={'point','highlight','freetext','strikeout','freehand','area'}
    colors=set(ANNOTATION_COLORS)
    def number(value):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
            raise ValidationError('첨삭 위치는 페이지 안에 있어야 합니다.')
        return round(value,6)
    result=[];seen=set();point_count=0
    for item in raw:
        if not isinstance(item,dict):raise ValidationError('첨삭 데이터가 올바르지 않습니다.')
        try:
            ident=str(UUID(str(item.get('id',''))));kind=item['type'];page=item['page']
            if ident in seen or kind not in allowed_types or type(page) is not int or not 1<=page<=page_count:raise ValueError
            seen.add(ident)
            color=item.get('color','#dc2626');size=item.get('size',16);width=item.get('width',4)
            if color not in colors or type(size) not in (int,float) or not math.isfinite(size) or not 10<=size<=32:raise ValueError
            if type(width) is not int or width not in ANNOTATION_WIDTHS:raise ValueError
            text=item.get('text','')
            if not isinstance(text,str) or len(text)>2000:raise ValueError
            cleaned={'id':ident,'type':kind,'page':page,'color':color,'size':size,'width':width,'text':text,
              'x':number(item.get('x',0)),'y':number(item.get('y',0)),
              'w':number(item.get('w',0)),'h':number(item.get('h',0))}
            if cleaned['x']+cleaned['w']>1.000002 or cleaned['y']+cleaned['h']>1.000002:raise ValueError
            points=item.get('points',[])
            if not isinstance(points,list) or len(points)>3000:raise ValueError
            point_count+=len(points)
            if point_count>25000:raise ValueError
            cleaned['points']=[]
            for point in points:
                if not isinstance(point,list) or len(point)!=2:raise ValueError
                cleaned['points'].append([number(point[0]),number(point[1])])
            if kind=='freehand' and len(points)<2:raise ValueError
            # 글자를 드래그해 그은 형광펜·취소선: 줄마다 상자 하나(rects)와 고른 글(quote).
            if kind in TEXT_MARK_TYPES and item.get('rects') is not None:
                rects=item['rects']
                if not isinstance(rects,list) or not 1<=len(rects)<=200:raise ValueError
                cleaned['rects']=[]
                for rect in rects:
                    if not isinstance(rect,list) or len(rect)!=4:raise ValueError
                    x,y,w,h=(number(value) for value in rect)
                    if x+w>1.000002 or y+h>1.000002:raise ValueError
                    cleaned['rects'].append([x,y,w,h])
                quote=item.get('quote','')
                if not isinstance(quote,str) or len(quote)>1000:raise ValueError
                cleaned['quote']=quote
            result.append(cleaned)
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            raise ValidationError('첨삭 도구·좌표·색상·굵기를 확인하세요.') from exc
    return result
