from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.integrations.urls import api_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.reports.urls', namespace='reports')),
    path('usuarios/', include('apps.users.urls', namespace='users')),
    path('leads/', include('apps.leads.urls', namespace='leads')),
    path('tareas/', include('apps.tasks.urls', namespace='tasks')),
    path('cotizaciones/', include('apps.quotes.urls', namespace='quotes')),
    path('whatsapp/', include('apps.whatsapp.urls', namespace='whatsapp')),
    path('campanas/', include('apps.campaigns.urls', namespace='campaigns')),
    path('reportes/', include('apps.reports.urls_reports', namespace='reports_detail')),
    path('automatizaciones/', include('apps.automations.urls', namespace='automations')),
    path('integraciones/', include('apps.integrations.urls', namespace='integrations')),
    path('clientes/', include('apps.clientes.urls', namespace='clientes')),
    path('chatbot/', include('apps.chatbot.urls', namespace='chatbot')),
    # Public REST API (no namespace conflict — api_urlpatterns has no app_name)
    path('api/v1/', include(api_urlpatterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

handler404 = 'apps.reports.views.error_404'
handler500 = 'apps.reports.views.error_500'
