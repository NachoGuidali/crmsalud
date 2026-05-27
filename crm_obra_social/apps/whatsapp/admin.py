from django.contrib import admin
from .models import Conversacion, Mensaje, PlantillaHSM, LogAPIWhatsApp


@admin.register(Conversacion)
class ConversacionAdmin(admin.ModelAdmin):
    list_display = ('telefono', 'nombre_contacto', 'lead', 'agente', 'mensajes_no_leidos', 'ultimo_mensaje_at')
    list_filter = ('agente',)
    search_fields = ('telefono', 'nombre_contacto')
    raw_id_fields = ('lead', 'agente')


@admin.register(Mensaje)
class MensajeAdmin(admin.ModelAdmin):
    list_display = ('conversacion', 'direccion', 'tipo', 'status', 'timestamp')
    list_filter = ('direccion', 'tipo', 'status')
    search_fields = ('conversacion__telefono', 'contenido')
    readonly_fields = ('whatsapp_message_id', 'timestamp')


@admin.register(PlantillaHSM)
class PlantillaHSMAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'idioma', 'activa')
    list_filter = ('activa',)


@admin.register(LogAPIWhatsApp)
class LogAPIWhatsAppAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'method', 'response_status', 'exitoso', 'duracion_ms', 'created_at')
    list_filter = ('exitoso', 'method')
    readonly_fields = ('created_at',)
