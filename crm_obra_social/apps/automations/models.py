from django.conf import settings
from django.db import models


class ReglaAutomatizacion(models.Model):
    # --- Trigger types ---
    TRIGGER_TIEMPO_CREACION = 'tiempo_desde_creacion'
    TRIGGER_TIEMPO_SIN_CAMBIO = 'tiempo_sin_cambio'
    TRIGGER_TIEMPO_SIN_WA = 'tiempo_sin_respuesta_wa'
    TRIGGER_CHOICES = [
        (TRIGGER_TIEMPO_CREACION, 'N días desde que ingresó el lead'),
        (TRIGGER_TIEMPO_SIN_CAMBIO, 'N días sin actividad en el lead'),
        (TRIGGER_TIEMPO_SIN_WA, 'N días sin respuesta de WhatsApp del cliente'),
    ]

    # --- Action types ---
    ACCION_CAMBIAR_ESTADO = 'cambiar_estado'
    ACCION_CAMBIAR_PRIORIDAD = 'cambiar_prioridad'
    ACCION_ENVIAR_PLANTILLA_WA = 'enviar_plantilla_wa'
    ACCION_CREAR_TAREA = 'crear_tarea'
    ACCION_CHOICES = [
        (ACCION_CAMBIAR_ESTADO, 'Cambiar estado del lead'),
        (ACCION_CAMBIAR_PRIORIDAD, 'Cambiar prioridad del lead'),
        (ACCION_ENVIAR_PLANTILLA_WA, 'Enviar plantilla de WhatsApp'),
        (ACCION_CREAR_TAREA, 'Crear tarea para el agente asignado'),
    ]

    nombre = models.CharField(max_length=200, verbose_name='Nombre de la regla')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    activa = models.BooleanField(default=True, verbose_name='Activa', db_index=True)
    orden = models.PositiveSmallIntegerField(default=0, verbose_name='Orden de ejecución')

    # Trigger
    trigger_tipo = models.CharField(max_length=30, choices=TRIGGER_CHOICES, verbose_name='Disparador')
    trigger_dias = models.PositiveSmallIntegerField(verbose_name='Días', help_text='Número de días para el disparador')

    # Conditions (optional filters — all must match)
    condicion_estado = models.CharField(
        max_length=20, blank=True, verbose_name='Solo si estado es',
        help_text='Dejar vacío para cualquier estado',
    )
    condicion_prioridad = models.CharField(
        max_length=10, blank=True, verbose_name='Solo si prioridad es',
        help_text='Dejar vacío para cualquier prioridad',
    )
    condicion_origen = models.CharField(
        max_length=20, blank=True, verbose_name='Solo si origen es',
        help_text='Dejar vacío para cualquier origen',
    )

    # Action
    accion_tipo = models.CharField(max_length=30, choices=ACCION_CHOICES, verbose_name='Acción')
    accion_estado_destino = models.CharField(
        max_length=20, blank=True, verbose_name='Estado destino',
        help_text='Para acción "cambiar estado"',
    )
    accion_prioridad_destino = models.CharField(
        max_length=10, blank=True, verbose_name='Prioridad destino',
        help_text='Para acción "cambiar prioridad"',
    )
    accion_plantilla = models.ForeignKey(
        'whatsapp.PlantillaHSM', null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='Plantilla HSM', help_text='Para acción "enviar plantilla WhatsApp"',
    )
    accion_tarea_descripcion = models.TextField(
        blank=True, verbose_name='Descripción de la tarea',
        help_text='Para acción "crear tarea". Podés usar {lead} para el nombre del lead.',
    )
    accion_tarea_dias_plazo = models.PositiveSmallIntegerField(
        default=1, verbose_name='Plazo de la tarea (días)',
        help_text='Días desde hoy para la fecha programada de la tarea',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Regla de automatización'
        verbose_name_plural = 'Reglas de automatización'
        ordering = ['orden', 'nombre']

    def __str__(self):
        estado = '✅' if self.activa else '⏸'
        return f'{estado} {self.nombre}'


class AutomatizacionLog(models.Model):
    """Tracks which rules were applied to which leads to avoid duplicates."""
    regla = models.ForeignKey(ReglaAutomatizacion, on_delete=models.CASCADE, related_name='logs')
    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='automatizacion_logs')
    ejecutado_at = models.DateTimeField(auto_now_add=True)
    resultado = models.TextField(blank=True)
    exitoso = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Log de automatización'
        verbose_name_plural = 'Logs de automatización'
        ordering = ['-ejecutado_at']
        unique_together = [('regla', 'lead')]
