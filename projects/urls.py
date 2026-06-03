from django.urls import path
from . import views

urlpatterns = [
    path('', views.projects, name="projects"),
    path('project/<str:pk>/', views.project, name="project"),

    path('create-project/', views.createProject, name="create-project"),
    path('delete-project/<str:pk>/', views.delete_project, name="delete-project"),
    path('edit-project/<str:pk>/', views.edit_project, name="edit-project")

]