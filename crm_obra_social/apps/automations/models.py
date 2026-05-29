from django.conf import settings
from django.db import models


class ReglaAutomatizacion(models.Model):
    # --- Trigger types ---
    TRIGGER_TIEMPO_CREACION   = 'tiempo_desde_creacion'
    TRIGGER_TIEMPO_SIN_CAMBIO = 'tiempo_sin_cambio'
    TRIGGER_TIEMPO_SIN_WA     = 'tiempo_sin_respuesta_wa'
    TRIGGER_ESTADO_CAMBIO     = 'estado_cambio'
    TRIGGER_CHOICES = [
        (TRIGGER_TIEMPO_CREACION,   'N días desde que ingresó el lead'),
        (TRIGGER_TIEMPO_SIN_CAMBIO, 'N días sin actividad en el lead'),
        (TRIGGER_TIEMPO_SIN_WA,     'N días sin respuesta de WhatsApp del cliente'),
        (TRIGGER_ESTADO_CAMBIO,     'Cuando un campo del lead cambia de valor'),
    ]

    # --- Action types ---
    ACCION_CAMBIAR_ESTADO     = 'cambiar_estado'
    ACCION_CAMBIAR_PRIORIDAD  = 'cambiar_prioridad'
    ACCION_ENVIAR_PLANTILLA_WA = 'enviar_plantilla_wa'
    ACCION_CREAR_TAREA        = 'crear_tarea'
    ACCION_ENVIAR_MENSAJE_WA  = 'enviar_mensaje_wa'
    ACCION_ASIGNAR_AGENTE     = 'asignar_agente'
    ACCION_LLAMAR_WEBHOOK     = 'llamar_webhook'
    ACCION_CONVERTIR_CLIENTE  = 'convertir_cliente'
    ACCION_CHOICES = [
        (ACCION_CAMBIAR_ESTADO,      'Cambiar estado del lead'),
        (ACCION_CAMBIAR_PRIORIDAD,   'Cambiar prioridad del lead'),
        (ACCION_ENVIAR_PLANTILLA_WA, 'Enviar plantilla de WhatsApp'),
        (ACCION_CREAR_TAREA,         'Crear tarea para el agente asignado'),
        (ACCION_ENVIAR_MENSAJE_WA,   'Enviar mensaje de WhatsApp (texto libre)'),
        (ACCION_ASIGNAR_AGENTE,      'Asignar agente al lead'),
        (ACCION_LLAMAR_WEBHOOK,      'Llamar webhook externo (n8n / URL)'),
        (ACCION_CONVERTIR_CLIENTE,   'Convertir lead a Cliente automáticamente'),
    ]

    nombre     = models.CharField(max_length=200, verbose_name='Nombre de la regla')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    activa     = models.BooleanField(default=True, verbose_name='Activa', db_index=True)
    orden      = models.PositiveSmallIntegerField(default=0, verbose_name='Orden de ejecución')

    # Trigger — time-based
    trigger_tipo = models.CharField(max_length=30, choices=TRIGGER_CHOICES, verbose_name='Disparador')
    trigger_dias = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name='Días', help_text='Número de días (solo para disparadores por tiempo)',
    )

    # Trigger — event-based (used when trigger_tipo == TRIGGER_ESTADO_CAMBIO)
    trigger_campo           = models.CharField(max_length=50, blank=True, default='estado',
                                               verbose_name='Campo que cambia',
                                               help_text='Campo del lead (ej: estado, prioridad)')
    trigger_valor_anterior  = models.CharField(max_length=100, blank=True,
                                               verbose_name='Valor anterior',
                                               help_text='Dejar vacío para "cualquier valor anterior"')
    trigger_valor_nuevo     = models.CharField(max_length=100, blank=True,
                                               verbose_name='Valor nuevo',
                                               help_text='Valor al que cambia el campo')

    # Conditions (optional filters — all must match)
    condicion_estado    = models.CharField(max_length=20, blank=True, verbose_name='Solo si estado es',
                                           help_text='Dejar vacío para cualquier estado')
    condicion_prioridad = models.CharField(max_length=10, blank=True, verbose_name='Solo si prioridad es',
                                           help_text='Dejar vacío para cualquier prioridad')
    condicion_origen    = models.CharField(max_length=20, blank=True, verbose_name='Solo si origen es',
                                           help_text='Dejar vacío para cualquier origen')

    # Action — common
    accion_tipo = models.CharField(max_length=30, choices=ACCION_CHOICES, verbose_name='Acción')

    # cambiar_estado
    accion_estado_destino = models.CharField(max_length=20, blank=True, verbose_name='Estado destino',
                                             help_text='Para acción "cambiar estado"')
    # cambiar_prioridad
    accion_prioridad_destino = models.CharField(max_length=10, blank=True, verbose_name='Prioridad destino',
                                                help_text='Para acción "cambiar prioridad"')
    # enviar_plantilla_wa
    accion_plantilla = models.ForeignKey(
        'whatsapp.PlantillaHSM', null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='Plantilla HSM', help_text='Para acción "enviar plantilla WhatsApp"',
    )
    # crear_tarea
    accion_tarea_descripcion = models.TextField(blank=True, verbose_name='Descripción de la tarea',
                                                help_text='Podés usar {lead} para el nombre del lead.')
    accion_tarea_dias_plazo  = models.PositiveSmallIntegerField(default=1, verbose_name='Plazo (días)',
                                                                help_text='Días desde hoy para la tarea')
    # enviar_mensaje_wa
    accion_mensaje_texto = models.TextField(blank=True, verbose_name='Texto del mensaje',
                                            help_text='Podés usar {lead}, {estado}, {telefono}')
    # asignar_agente
    accion_agente = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='automatizaciones_asignadas', verbose_name='Agente a asignar',
    )
    # llamar_webhook
    accion_webhook_url = models.CharField(max_length=500, blank=True, verbose_name='URL del webhook')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Regla de automatización'
        verbose_name_plural = 'Reglas de automatización'
        ordering = ['orden', 'nombre']

    def __str__(self):
        estado = '✅' if self.activa else '⏸'
        return f'{estado} {self.nombre}'

    @property
    def es_event_based(self):
        return self.trigger_tipo == self.TRIGGER_ESTADO_CAMBIO


class AutomatizacionLog(models.Model):
    """Tracks automation rule executions per lead."""
    regla       = models.ForeignKey(ReglaAutomatizacion, on_delete=models.CASCADE, related_name='logs')
    lead        = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='automatizacion_logs')
    ejecutado_at = models.DateTimeField(auto_now_add=True)
    resultado   = models.TextField(blank=True)
    exitoso     = models.BooleanField(default=True)
    evento      = models.CharField(max_length=200, blank=True,
                                   help_text='Descripción del evento que disparó (para event-based)')

    class Meta:
        verbose_name = 'Log de automatización'
        verbose_name_plural = 'Logs de automatización'
        ordering = ['-ejecutado_at']
