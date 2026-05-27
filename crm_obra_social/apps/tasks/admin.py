from django.contrib import admin
from .models import Tarea


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'lead', 'agente', 'fecha_programada', 'status')
    list_filter = ('tipo', 'status')
    search_fields = ('lead__nombre_completo', 'descripcion')
    raw_id_fields = ('lead', 'agente')
