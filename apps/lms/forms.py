
from apps.lms.ui_forms import PublishOnCreateMixin
from pathlib import Path
import zipfile
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.accounts.models import User
from apps.students.forms import StudentSelectionField
from .models import ClassPost, RoomSettings

DOCUMENT_EXTENSIONS = {'.pdf','.jpg','.jpeg','.png','.webp','.doc','.docx','.ppt','.pptx','.xls','.xlsx','.txt','.csv'}
RESOURCE_EXTENSIONS = DOCUMENT_EXTENSIONS | {'.mp3','.wav','.m4a','.ogg','.flac','.zip'}


def validate_file(upload, resource=False):
    if not upload or not hasattr(upload, 'chunks'):
        return upload
    limit = min(100, max(1, int(getattr(settings,'LMS_UPLOAD_MAX_MB',25)))) * 1024 * 1024
    if upload.size <= 0 or upload.size > limit:
        raise ValidationError(f'파일은 1바이트 이상 {limit//(1024*1024)}MB 이하로 업로드하세요.')
    ext = Path(upload.name).suffix.lower()
    if ext not in (RESOURCE_EXTENSIONS if resource else DOCUMENT_EXTENSIONS):
        raise ValidationError('허용되지 않는 파일 형식입니다. 실행파일·HTML·매크로 문서는 등록할 수 없습니다.')
    pos = upload.tell()
    try:
        upload.seek(0); header = upload.read(16); upload.seek(0)
        if ext == '.pdf' and not header.startswith(b'%PDF-'):
            raise ValidationError('확장자만 PDF인 파일은 업로드할 수 없습니다.')
        if ext in {'.jpg','.jpeg','.png','.webp'}:
            from PIL import Image
            try:
                with Image.open(upload) as image:
                    if image.width * image.height > 24_000_000:
                        raise ValidationError('이미지는 2,400만 화소 이하로 업로드하세요.')
                    image.verify()
            except ValidationError: raise
            except Exception as exc:
                raise ValidationError('이미지 파일이 손상되었거나 형식이 맞지 않습니다.') from exc
        if ext in {'.docx','.pptx','.xlsx'}:
            try:
                with zipfile.ZipFile(upload) as archive:
                    infos = archive.infolist()
                    if len(infos)>10000 or sum(i.file_size for i in infos)>200*1024*1024:
                        raise ValidationError('압축 해제 크기가 너무 큰 문서는 등록할 수 없습니다.')
                    names={i.filename for i in infos}
                    required={'.docx':'word/document.xml','.pptx':'ppt/presentation.xml','.xlsx':'xl/workbook.xml'}[ext]
                    if required not in names or any('vbaproject' in n.lower() for n in names):
                        raise ValidationError('문서 형식이 일치하지 않거나 매크로가 포함되어 있습니다.')
            except (zipfile.BadZipFile, OSError) as exc:
                raise ValidationError('Office 문서가 손상되었습니다.') from exc
        if ext in {'.doc','.ppt','.xls'} and not header.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
            raise ValidationError('구형 Office 파일 형식이 일치하지 않습니다.')
    finally:
        upload.seek(pos)
    return upload


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def __init__(self,*args,resource=False,**kwargs):
        kwargs.setdefault('widget',MultiFileInput(attrs={'class':'form-control'}))
        kwargs.setdefault('required',False)
        self.resource=resource
        super().__init__(*args,**kwargs)
    def clean(self,data,initial=None):
        files = list(data) if isinstance(data,(tuple,list)) else ([data] if data else [])
        if len(files)>5:
            raise ValidationError('한 번에 파일은 최대 5개까지 선택하세요.')
        cleaned=[super(MultiFileField,self).clean(f,initial) for f in files]
        if sum(f.size for f in cleaned)>80*1024*1024:
            raise ValidationError('전체 업로드는 80MB 이하로 선택하세요.')
        for f in cleaned: validate_file(f,resource=self.resource)
        return cleaned


class RoomForm(forms.ModelForm):
    class Meta:
        model=RoomSettings
        fields=['schedule','zoom_url','dsg_guide','classroom_url','canvas_url']
        widgets={'schedule':forms.Textarea(attrs={'rows':3}),'dsg_guide':forms.Textarea(attrs={'rows':4})}
    def clean(self):
        values=super().clean()
        for key in ('zoom_url','classroom_url','canvas_url'):
            value=values.get(key,'')
            if value and not value.lower().startswith('https://'):
                self.add_error(key,'https://로 시작하는 주소를 입력하세요.')
        return values


class RosterForm(forms.Form):
    student_ids=StudentSelectionField()
    staff=forms.ModelMultipleChoiceField(label='담당 TA·공동 강사', required=False,
        queryset=User.objects.none(), widget=forms.SelectMultiple(attrs={'size':6}))
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['student_ids'].required=False
        self.fields['staff'].queryset=User.objects.filter(is_active=True,role__in=[User.Role.TEACHER,User.Role.TA]).order_by('role','display_name','username')
        self.fields['staff'].help_text='강사 계정은 이 반의 공지·과제·퀴즈·첨삭을 함께 작업합니다. TA(조교) 계정은 이 반 학생 정보·반별 학습(공지·과제·토론·퀴즈·자료)을 함께 보고 올리며, 리포트카드 작성까지 합니다(발송은 관리자).'


class PostForm(PublishOnCreateMixin, forms.ModelForm):
    publication_field = "published"
    uploads=MultiFileField(label='첨부파일 (최대 5개)',resource=True)
    class Meta:
        model=ClassPost
        fields=['kind','title','body','published','pinned']
        widgets={'body':forms.Textarea(attrs={'rows':9})}
    def clean(self):
        values=super().clean()
        if not values.get('body','').strip() and not values.get('uploads') and not(self.instance.pk and self.instance.files.exists()):
            self.add_error('body','내용 또는 파일을 입력하세요.')
        return values


class GradeForm(forms.Form):
    score=forms.DecimalField(label='점수',max_digits=10,decimal_places=2,min_value=0,required=False)
    feedback=forms.CharField(label='총평·피드백',required=False,max_length=20000,widget=forms.Textarea(attrs={'rows':5}))
    version=forms.CharField(widget=forms.HiddenInput())
    def __init__(self,*args,maximum=0,**kwargs):
        self.maximum=maximum
        super().__init__(*args,**kwargs)
        self.fields['score'].widget.attrs.update({'max':str(maximum),'step':'0.01'})
    def clean_score(self):
        score=self.cleaned_data.get('score')
        if score is not None and score>self.maximum:
            raise ValidationError(f'배점 {self.maximum}점을 초과할 수 없습니다.')
        return score


class MessageForm(forms.Form):
    body=forms.CharField(label='메시지',max_length=4000,widget=forms.Textarea(attrs={'rows':2, 'placeholder':'메시지 입력…', 'maxlength':4000, 'data-chat-input':'true'}))
    client_token=forms.UUIDField(widget=forms.HiddenInput())


class ContactChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, user):
        return user.chat_name


class ConversationForm(forms.Form):
    # 체크 목록 + 이름 검색(lms/js/new-chat.js). 강사·관리자가 두 명 이상 고르면 그룹 대화가 됩니다.
    recipients=ContactChoiceField(label='대화할 사람',queryset=User.objects.none(),widget=forms.CheckboxSelectMultiple)


class PrivateFileInput(forms.ClearableFileInput):
    """Never expose storage URLs or long internal paths in a submission form."""
    template_name = 'lms/widgets/private_file.html'
