"""Bounded local document worker. No shell, network service or public file URLs.
Runs as a subprocess so a bad PDF does not take down the WSGI worker.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings

from PIL import Image, ImageDraw, ImageFont


def font(size):
    candidates = [os.environ.get('LMS_FONT_PATH',''),
      'C:/Windows/Fonts/malgun.ttf','C:/Windows/Fonts/arial.ttf',
      '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
      '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
      '/System/Library/Fonts/AppleSDGothicNeo.ttc']
    for name in candidates:
        if name and Path(name).is_file():
            return ImageFont.truetype(name,size)
    return ImageFont.load_default()


def text_pdf(text, output):
    """Plain text/quiz answer preview, no invented scores/content."""
    width,height=1200,1696
    body_font=font(22)
    lines=[]
    for raw in text.splitlines():
        current=''
        for char in raw:
            if body_font.getlength(current+char)>1060:
                lines.append(current); current=char
            else: current+=char
        lines.append(current)
    if len(lines)>4300: raise ValueError('텍스트가 너무 길어 미리보기를 만들 수 없습니다.')
    pages=[];layer={}
    for start in range(0,max(1,len(lines)),43):
        img=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(img);words=[]
        for i,line in enumerate(lines[start:start+43]):
            top=70+34*i
            draw.text((70,top),line,font=body_font,fill='#202938')
            # 그린 자리 그대로 단어 위치를 남깁니다(글자 드래그 형광펜·취소선용).
            for match in re.finditer(r'\S+',line):
                left=70+body_font.getlength(line[:match.start()]);right=left+body_font.getlength(match.group())
                _,y0,_,y1=body_font.getbbox(line or ' ')
                words.append({'t':match.group(),'x':round(left/width,5),'y':round((top+y0)/height,5),
                  'w':round((right-left)/width,5),'h':round(max(1,y1-y0)/height,5),'line':i})
        draw.text((70,1620),f'{start//43+1}',font=font(16),fill='#64748b')
        pages.append(img);layer[str(start//43+1)]=words
    pages[0].save(output,'PDF',save_all=True,append_images=pages[1:],resolution=144)
    for image in pages:image.close()
    Path(str(output)+'.words.json').write_text(json.dumps(layer,ensure_ascii=False),encoding='utf-8')


def page_words(page,limit=4000):
    """한 쪽의 단어와 위치(쪽 크기 대비 0~1, 위쪽 기준). 글자 층이 없는(스캔·이미지) 쪽은 빈 목록."""
    try:
        width,height=page.get_size();textpage=page.get_textpage()
        try:
            words,current,line,span=[],None,0,None
            for index in range(min(textpage.count_chars(),60000)):
                char=textpage.get_text_range(index,1)
                if char in ('\r','\n') or char.isspace():
                    if current:words.append(current);current=None
                    if char=='\n':line+=1;span=None
                    continue
                left,bottom,right,top=textpage.get_charbox(index)
                if right<=left or top<=bottom:continue
                # 줄바꿈 표시가 없어도 지금 줄의 높이 범위와 전혀 겹치지 않으면 새 줄로 봅니다(마침표·쉼표처럼 작은 글자는 같은 줄).
                if span is not None and (top<span[0] or bottom>span[1]):
                    if current:words.append(current);current=None
                    line+=1;span=None
                span=(min(span[0],bottom),max(span[1],top)) if span else (bottom,top)
                if current is None:current={'t':char,'l':left,'b':bottom,'r':right,'top':top,'line':line}
                else:current.update(t=current['t']+char,l=min(current['l'],left),b=min(current['b'],bottom),r=max(current['r'],right),top=max(current['top'],top))
                if len(words)>=limit:break
            if current and len(words)<limit:words.append(current)
        finally:textpage.close()
        # 줄 번호를 0부터 빈틈없이 다시 매깁니다.
        lines={value:number for number,value in enumerate(sorted({w['line'] for w in words}))}
        clip=lambda v:min(1,max(0,v))
        return [{'t':w['t'],'x':round(clip(w['l']/width),5),'y':round(clip((height-w['top'])/height),5),
                 'w':round(clip((w['r']-w['l'])/width),5),'h':round(clip((w['top']-w['b'])/height),5),'line':lines[w['line']]}
                for w in words]
    finally:page.close()


def convert(input_path,output,converter=''):
    ext=input_path.suffix.lower()
    if ext=='.pdf':
        output.write_bytes(input_path.read_bytes())
    elif ext in {'.png','.jpg','.jpeg','.webp'}:
        with Image.open(input_path) as image:
            if image.width*image.height>24_000_000:raise ValueError('이미지 크기가 너무 큽니다.')
            if image.mode=='RGBA':
                rgb=Image.new('RGB',image.size,'white');rgb.paste(image,mask=image.getchannel('A'))
            else:rgb=image.convert('RGB')
            rgb.save(output,'PDF',resolution=144);rgb.close()
    elif ext=='.txt':
        text_pdf(input_path.read_text('utf-8-sig',errors='replace'),output)
    elif ext in {'.doc','.docx','.ppt','.pptx'}:
        if not converter or not Path(converter).is_file():
            raise ValueError('Word·PPT 자동 미리보기에는 로컬 문서 변환기 설정이 필요합니다. 원본 제출은 유지하고, PDF로 저장한 첨삭용 미리보기를 아래에서 등록할 수 있습니다.')
        with tempfile.TemporaryDirectory(prefix='edutrack-office-') as tmp:
            tmp=Path(tmp);profile=tmp/'profile';profile.mkdir()
            # Macro security highest; no external link refresh. Use a disposable profile.
            user=profile/'user';user.mkdir()
            (user/'registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Common/Load"><prop oor:name="UpdateLinks" oor:op="fuse"><value>0</value></prop></item></oor:items>''',encoding='utf-8')
            cmd=[str(converter),f'-env:UserInstallation={profile.as_uri()}','--headless','--nologo','--nodefault','--norestore','--nolockcheck','--convert-to','pdf','--outdir',str(tmp),str(input_path)]
            result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=50,shell=False)
            pdf=tmp/(input_path.stem+'.pdf')
            if result.returncode or not pdf.is_file():raise ValueError('문서 변환에 실패했습니다. PDF 미리보기를 직접 등록하세요.')
            output.write_bytes(pdf.read_bytes())
    elif ext in {'.xls','.xlsx','.csv'}:
        raise ValueError('Excel·표 파일은 원본을 보존합니다. 수식·시트·인쇄영역을 임의로 바꾸지 않도록, Excel에서 PDF로 저장한 첨삭용 미리보기를 등록하세요.')
    else:
        raise ValueError('이 형식은 원본 다운로드만 지원합니다. PDF 미리보기를 등록하세요.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['convert','render','info','text','words'])
    parser.add_argument('source');parser.add_argument('output');parser.add_argument('--page',type=int,default=1)
    parser.add_argument('--converter',default='');args=parser.parse_args()
    source=Path(args.source);output=Path(args.output)
    if source.stat().st_size>30*1024*1024:raise ValueError('미리보기 원본은 30MB 이하로 제한됩니다.')
    if args.mode=='text':text_pdf(source.read_text('utf-8'),output)
    elif args.mode=='convert':convert(source,output,args.converter)
    else:
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(source) as doc:
            if len(doc)>100 or len(doc)==0:raise ValueError('PDF 미리보기는 1~100페이지를 지원합니다.')
            if args.mode=='info':
                sizes=[doc.get_page_size(i) for i in range(len(doc))]
                if any(w<=0 or h<=0 or w>14400 or h>14400 for w,h in sizes):raise ValueError('PDF 페이지 크기가 유효하지 않습니다.')
                output.write_text(json.dumps({'pages':len(doc),'sizes':sizes}));return
            if not 1<=args.page<=len(doc):raise ValueError('페이지 번호가 올바르지 않습니다.')
            if args.mode=='words':
                output.write_text(json.dumps({'words':page_words(doc[args.page-1])},ensure_ascii=False),encoding='utf-8');return
            page=doc[args.page-1]
            try:
                w,h=page.get_size();scale=min(2.0,1500/max(w,h))
                bitmap=page.render(scale=scale)
                try:
                    image=bitmap.to_pil();image.save(output,'PNG');image.close()
                finally:bitmap.close()
            finally:page.close()

if __name__=='__main__':
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            main()
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:600]},ensure_ascii=True),file=sys.stderr)
        sys.exit(2)
