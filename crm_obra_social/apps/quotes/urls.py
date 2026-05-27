from django.urls import path
from . import views

app_name = 'quotes'

urlpatterns = [
    path('nueva/', views.CotizacionCreateView.as_view(), name='create'),
    path('<int:pk>/', views.CotizacionDetailView.as_view(), name='detail'),
    path('<int:pk>/pdf/', views.CotizacionPDFView.as_view(), name='pdf'),
    path('<int:pk>/enviar-whatsapp/', views.CotizacionWhatsAppSendView.as_view(), name='send_whatsapp'),
]
