from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('', views.BotListView.as_view(), name='list'),
    path('nuevo/', views.BotCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.BotUpdateView.as_view(), name='update'),
    path('<int:pk>/eliminar/', views.BotDeleteView.as_view(), name='delete'),
    path('<int:pk>/toggle/', views.BotToggleView.as_view(), name='toggle'),
    path('<int:pk>/builder/', views.BotBuilderView.as_view(), name='builder'),
    path('<int:pk>/flow/', views.BotFlowAPIView.as_view(), name='flow_api'),
]
