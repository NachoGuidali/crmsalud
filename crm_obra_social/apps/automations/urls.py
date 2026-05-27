from django.urls import path
from . import views

app_name = 'automations'

urlpatterns = [
    path('', views.ReglaListView.as_view(), name='list'),
    path('nueva/', views.ReglaCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.ReglaUpdateView.as_view(), name='update'),
    path('<int:pk>/toggle/', views.ReglaToggleView.as_view(), name='toggle'),
    path('<int:pk>/ejecutar/', views.ReglaEjecutarView.as_view(), name='ejecutar'),
    path('<int:pk>/eliminar/', views.ReglaDeleteView.as_view(), name='delete'),
    path('logs/', views.LogListView.as_view(), name='logs'),
]
