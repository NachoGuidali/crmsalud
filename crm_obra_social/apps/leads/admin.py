from django.contrib import admin
from .models import Lead, HistorialEstado, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo')
    list_editable = ('activo',)


class HistorialEstadoInline(admin.TabularInline):
    model = HistorialEstado
    extra = 0
    readonly_fields = ('estado_anterior', 'estado_nuevo', 'cambiado_por', 'nota', 'created_at')
    can_delete = False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'dni', 'telefono', 'estado', 'prioridad', 'agente', 'created_at')
    list_filter = ('estado', 'prioridad', 'origen', 'provincia')
    search_fields = ('nombre_completo', 'dni', 'telefono', 'email')
    raw_id_fields = ('agente',)
    inlines = [HistorialEstadoInline]
    readonly_fields = ('created_at', 'updated_at')
