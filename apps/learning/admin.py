from django.contrib import admin

from .models import (
    Discussion,
    DiscussionComment,
    DiscussionRecipient,
    LearningGroup,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    QuizRecipient,
)

admin.site.register(LearningGroup)
admin.site.register(Discussion)
admin.site.register(DiscussionRecipient)
admin.site.register(DiscussionComment)
admin.site.register(Quiz)
admin.site.register(QuizRecipient)
admin.site.register(QuizQuestion)
admin.site.register(QuizChoice)
admin.site.register(QuizAttempt)
admin.site.register(QuizAnswer)
