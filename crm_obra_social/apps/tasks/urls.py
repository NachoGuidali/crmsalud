from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.TareaListView.as_view(), name='list'),
    path('agenda/', views.AgendaView.as_view(), name='agenda'),
    path('nueva/', views.TareaCreateView.as_view(), name='create'),
    path('<int:pk>/completar/', views.TareaCompletarView.as_view(), name='completar'),
]
