from django.urls import path
from . import views

app_name = 'integrations'

# Admin UI
urlpatterns = [
    path('', views.ApiKeyListView.as_view(), name='list'),
    path('nueva-clave/', views.ApiKeyCreateView.as_view(), name='apikey_create'),
    path('<int:pk>/toggle/', views.ApiKeyToggleView.as_view(), name='apikey_toggle'),
    path('<int:pk>/eliminar/', views.ApiKeyDeleteView.as_view(), name='apikey_delete'),
    path('documentacion/', views.ApiDocsView.as_view(), name='docs'),
]

# Public REST API
api_urlpatterns = [
    path('leads/', views.LeadCreateAPIView.as_view(), name='api_leads_create'),
    path('leads/actualizar/', views.LeadUpdateAPIView.as_view(), name='api_leads_update'),
    path('leads/buscar/', views.LeadSearchAPIView.as_view(), name='api_leads_search'),
    path('leads/<int:pk>/', views.LeadStatusAPIView.as_view(), name='api_leads_status'),
    path('webhook/<str:source>/', views.GenericWebhookView.as_view(), name='api_webhook'),
]
