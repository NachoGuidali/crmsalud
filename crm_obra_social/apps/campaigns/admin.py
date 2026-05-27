from django.contrib import admin
from .models import Campana, CampanaLog


@admin.register(Campana)
class CampanaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'plantilla', 'status', 'total_destinatarios', 'enviados', 'errores', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('total_destinatarios', 'enviados', 'entregados', 'leidos', 'errores', 'created_at', 'updated_at')


@admin.register(CampanaLog)
class CampanaLogAdmin(admin.ModelAdmin):
    list_display = ('campana', 'telefono', 'status', 'created_at')
    list_filter = ('status',)
