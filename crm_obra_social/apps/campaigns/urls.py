from django.urls import path
from . import views

app_name = 'campaigns'

urlpatterns = [
    path('', views.CampanaListView.as_view(), name='list'),
    path('nueva/', views.CampanaCreateView.as_view(), name='create'),
    path('<int:pk>/', views.CampanaDetailView.as_view(), name='detail'),
    path('<int:pk>/lanzar/', views.CampanaLanzarView.as_view(), name='lanzar'),
    path('<int:pk>/eliminar/', views.CampanaDeleteView.as_view(), name='delete'),
    path('api/contactos/', views.ContactoBuscarView.as_view(), name='api_contactos'),
    path('api/preview-count/', views.CampanaPreviewCountView.as_view(), name='api_preview_count'),
]
