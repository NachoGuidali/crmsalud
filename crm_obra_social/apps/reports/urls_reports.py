from django.urls import path
from . import views

app_name = 'reports_detail'

urlpatterns = [
    path('conversion/', views.ReporteConversionView.as_view(), name='conversion'),
    path('mensajes/', views.ReporteMensajesView.as_view(), name='mensajes'),
    path('exportar/', views.ReporteExportCSVView.as_view(), name='exportar'),
]
