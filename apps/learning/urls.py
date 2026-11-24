from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("groups/", views.group_manage, name="group-manage"),
    path("groups/<int:group_id>/edit/", views.group_update, name="group-update"),
    path("discussions/", views.discussion_list, name="discussion-list"),
    path("discussions/new/", views.discussion_create, name="discussion-create"),
    path("discussions/<int:discussion_id>/", views.discussion_detail, name="discussion-detail"),
    path("discussions/<int:discussion_id>/edit/", views.discussion_update, name="discussion-update"),
    path("my/discussions/", views.my_discussions, name="my-discussions"),
    path("my/discussions/<int:recipient_id>/", views.my_discussion_detail, name="my-discussion-detail"),
    path("quizzes/", views.quiz_list, name="quiz-list"),
    path("quizzes/new/", views.quiz_create, name="quiz-create"),
    path("quizzes/<int:quiz_id>/", views.quiz_detail, name="quiz-detail"),
    path("quizzes/<int:quiz_id>/edit/", views.quiz_update, name="quiz-update"),
    path("quizzes/<int:quiz_id>/questions/new/", views.quiz_question_create, name="quiz-question-create"),
    path("quizzes/<int:quiz_id>/questions/<int:question_id>/edit/", views.quiz_question_update, name="quiz-question-update"),
    path("quizzes/<int:quiz_id>/questions/<int:question_id>/delete/", views.quiz_question_delete, name="quiz-question-delete"),
    path("my/quizzes/", views.my_quizzes, name="my-quizzes"),
    path("my/quizzes/<int:recipient_id>/", views.my_quiz_detail, name="my-quiz-detail"),
]
