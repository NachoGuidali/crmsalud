from django.contrib import admin
from .models import ApiKey, WebhookLog


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activa', 'origen_default', 'total_usos', 'ultimo_uso_at', 'created_at']
    list_filter = ['activa', 'origen_default']
    readonly_fields = ['key', 'total_usos', 'ultimo_uso_at', 'created_at']


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'api_key', 'endpoint', 'method', 'response_status', 'status', 'lead_creado']
    list_filter = ['status', 'method']
    readonly_fields = list(f.name for f in WebhookLog._meta.fields)
