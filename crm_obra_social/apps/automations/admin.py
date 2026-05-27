from django.contrib import admin
from .models import ReglaAutomatizacion, AutomatizacionLog


@admin.register(ReglaAutomatizacion)
class ReglaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activa', 'trigger_tipo', 'trigger_dias', 'accion_tipo', 'orden']
    list_filter = ['activa', 'trigger_tipo', 'accion_tipo']
    list_editable = ['activa', 'orden']


@admin.register(AutomatizacionLog)
class LogAdmin(admin.ModelAdmin):
    list_display = ['regla', 'lead', 'ejecutado_at', 'exitoso', 'resultado']
    list_filter = ['exitoso', 'regla']
    readonly_fields = ['regla', 'lead', 'ejecutado_at', 'resultado', 'exitoso']
