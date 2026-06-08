from django.conf import settings
from django.db import models


class ReglaAutomatizacion(models.Model):
    # --- Tipo de regla: separa "Automatización" (dispara por tiempo) de "Disparador" (por evento) ---
    TIPO_AUTOMATIZACION = 'automatizacion'
    TIPO_DISPARADOR     = 'disparador'
    TIPO_REGLA_CHOICES = [
        (TIPO_AUTOMATIZACION, 'Automatización'),
        (TIPO_DISPARADOR,     'Disparador'),
    ]

    # --- Trigger types — Automatización (dispara por tiempo) ---
    TRIGGER_INMEDIATO         = 'inmediato'
    TRIGGER_DELAY             = 'delay'
    TRIGGER_FECHA_CAMPO       = 'fecha_campo'
    TRIGGER_TIEMPO_SIN_CAMBIO = 'tiempo_sin_cambio'
    TRIGGER_TIEMPO_SIN_WA     = 'tiempo_sin_respuesta_wa'

    # --- Trigger types — Disparador (dispara por evento) ---
    TRIGGER_CREADO             = 'creado'
    TRIGGER_CAMPO_CAMBIA       = 'campo_cambia'
    TRIGGER_CAMPO_IGUAL_A      = 'campo_igual_a'
    TRIGGER_RESPONSABLE_CAMBIA = 'responsable_cambia'

    TRIGGER_CHOICES_AUTOMATIZACION = [
        (TRIGGER_INMEDIATO,         'Inmediatamente (al cumplirse la condición)'),
        (TRIGGER_DELAY,             'En X tiempo'),
        (TRIGGER_FECHA_CAMPO,       'Cuando un campo de fecha coincide con una referencia'),
        (TRIGGER_TIEMPO_SIN_CAMBIO, 'N días sin actividad en el lead'),
        (TRIGGER_TIEMPO_SIN_WA,     'N días sin respuesta de WhatsApp del cliente'),
    ]
    TRIGGER_CHOICES_DISPARADOR = [
        (TRIGGER_CREADO,             'Al crear el lead'),
        (TRIGGER_CAMPO_CAMBIA,       'Cuando un campo cambia (a cualquier valor nuevo)'),
        (TRIGGER_CAMPO_IGUAL_A,      'Cuando un campo pasa a valer un valor específico'),
        (TRIGGER_RESPONSABLE_CAMBIA, 'Cuando cambia el responsable (agente) del lead'),
    ]
    TRIGGER_CHOICES = TRIGGER_CHOICES_AUTOMATIZACION + TRIGGER_CHOICES_DISPARADOR

    DELAY_MINUTOS, DELAY_HORAS, DELAY_DIAS = 'minutos', 'horas', 'dias'
    DELAY_UNIDAD_CHOICES = [
        (DELAY_MINUTOS, 'Minutos'),
        (DELAY_HORAS,   'Horas'),
        (DELAY_DIAS,    'Días'),
    ]

    OFFSET_ANTES, OFFSET_DESPUES = 'antes', 'despues'
    OFFSET_SIGNO_CHOICES = [
        (OFFSET_ANTES,   'antes de'),
        (OFFSET_DESPUES, 'después de'),
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

    tipo_regla = models.CharField(max_length=15, choices=TIPO_REGLA_CHOICES,
                                  default=TIPO_AUTOMATIZACION, db_index=True,
                                  verbose_name='Tipo de regla')

    # Trigger — general
    trigger_tipo = models.CharField(max_length=30, choices=TRIGGER_CHOICES, verbose_name='Disparador')
    trigger_dias = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Días',
        help_text='Para "N días sin actividad" / "N días sin respuesta de WhatsApp"',
    )

    # Trigger — "En X tiempo" (tipo_regla=automatizacion, trigger_tipo=delay)
    delay_cantidad = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Cantidad')
    delay_unidad   = models.CharField(max_length=10, choices=DELAY_UNIDAD_CHOICES, blank=True,
                                      default=DELAY_DIAS, verbose_name='Unidad')

    # Trigger — "Cuando un campo de fecha coincide con una referencia"
    # (tipo_regla=automatizacion, trigger_tipo=fecha_campo)
    fecha_campo_objetivo = models.CharField(max_length=50, blank=True, verbose_name='Campo de fecha',
                                            help_text='Campo del lead, ej: fecha_nacimiento, created_at')
    fecha_campo_offset_dias  = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Offset (días)')
    fecha_campo_offset_signo = models.CharField(max_length=10, choices=OFFSET_SIGNO_CHOICES, blank=True,
                                                default=OFFSET_DESPUES, verbose_name='Offset')

    # Trigger — evento (tipo_regla=disparador)
    trigger_campo           = models.CharField(max_length=50, blank=True, default='estado',
                                               verbose_name='Campo',
                                               help_text='Campo del lead a observar (ej: estado, prioridad, agente)')
    trigger_valor_anterior  = models.CharField(max_length=100, blank=True,
                                               verbose_name='Valor anterior',
                                               help_text='Dejar vacío para "cualquier valor anterior"')
    trigger_valor_nuevo     = models.CharField(max_length=100, blank=True,
                                               verbose_name='Valor nuevo',
                                               help_text='Valor al que debe cambiar el campo')

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
        return self.tipo_regla == self.TIPO_DISPARADOR


class CondicionRegla(models.Model):
    """Condición genérica (campo · operador · valor) combinable con Y/O dentro de una regla."""
    OP_EQ, OP_NEQ, OP_GT, OP_LT, OP_CONTAINS, OP_EMPTY, OP_NOT_EMPTY = (
        'eq', 'neq', 'gt', 'lt', 'contains', 'empty', 'not_empty')
    OPERADOR_CHOICES = [
        (OP_EQ, 'es igual a'),
        (OP_NEQ, 'no es igual a'),
        (OP_GT, 'mayor que'),
        (OP_LT, 'menor que'),
        (OP_CONTAINS, 'contiene'),
        (OP_EMPTY, 'está vacío'),
        (OP_NOT_EMPTY, 'no está vacío'),
    ]

    JOIN_AND, JOIN_OR = 'AND', 'OR'
    JOIN_CHOICES = [
        (JOIN_AND, 'Y'),
        (JOIN_OR, 'O'),
    ]

    regla = models.ForeignKey(ReglaAutomatizacion, on_delete=models.CASCADE, related_name='condiciones')
    orden = models.PositiveSmallIntegerField(default=0)
    campo = models.CharField(max_length=50, verbose_name='Campo',
                             help_text="ej: estado, prioridad, origen, agente, plan_interes, cp:<slug>")
    operador = models.CharField(max_length=12, choices=OPERADOR_CHOICES, default=OP_EQ, verbose_name='Operador')
    valor = models.CharField(max_length=200, blank=True, verbose_name='Valor')
    join_siguiente = models.CharField(max_length=3, choices=JOIN_CHOICES, default=JOIN_AND,
                                      verbose_name='Unión con la siguiente',
                                      help_text='Cómo se combina con la condición que sigue (Y / O)')

    class Meta:
        verbose_name = 'Condición de regla'
        verbose_name_plural = 'Condiciones de regla'
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.campo} {self.get_operador_display()} {self.valor}'.strip()


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
