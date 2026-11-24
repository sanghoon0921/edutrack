from django.contrib import admin

from .models import Notice, NoticeAttachment, NoticeInlineImage, NoticeRead, Notification

admin.site.register(Notice)
admin.site.register(NoticeAttachment)
admin.site.register(NoticeInlineImage)
admin.site.register(NoticeRead)
admin.site.register(Notification)
