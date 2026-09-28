from django.urls import path
from . import views

app_name = 'tasks'
urlpatterns = [
    path('', views.projects, name='projects'),
    path('mine/', views.my_tasks, name='my_tasks'),
    path('new/', views.project_new, name='project_new'),
    path('<int:project_id>/', views.board, name='board'),
    path('<int:project_id>/settings/', views.project_settings, name='settings'),
    path('<int:project_id>/members/', views.member_add, name='member_add'),
    path('<int:project_id>/members/<int:user_id>/remove/', views.member_remove, name='member_remove'),
    path('<int:project_id>/tasks/new/', views.task_new, name='task_new'),
    path('<int:project_id>/tasks/<int:task_id>/', views.task_detail, name='task_detail'),
    path('<int:project_id>/tasks/<int:task_id>/move/', views.task_move, name='task_move'),
    path('<int:project_id>/tasks/<int:task_id>/delete/', views.task_delete, name='task_delete'),
]
