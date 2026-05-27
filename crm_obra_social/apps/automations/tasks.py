import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('apps.automations')


@shared_task
def ejecutar_automatizaciones():
    """
    Run all active automation rules against matching leads.
    Runs every hour via Celery Beat.
    """
    from .models import ReglaAutomatizacion, AutomatizacionLog
    from apps.leads.models import Lead

    reglas = ReglaAutomatizacion.objects.filter(activa=True).order_by('orden')
    now = timezone.now()
    total_ejecutadas = 0

    for regla in reglas:
        try:
            count = _ejecutar_regla(regla, now)
            total_ejecutadas += count
        except Exception as e:
            logger.error('Error ejecutando regla "%s": %s', regla.nombre, e)

    logger.info('Automatizaciones: %d acciones ejecutadas en %d reglas', total_ejecutadas, len(reglas))
    return f'{total_ejecutadas} acciones ejecutadas'


def _ejecutar_regla(regla, now):
    from .models import AutomatizacionLog
    from apps.leads.models import Lead

    delta = timedelta(days=regla.trigger_dias)
    ventana = timedelta(hours=2)  # execution window to catch missed runs

    # Base queryset — exclude terminal states
    qs = Lead.objects.exclude(estado__in=['afiliado', 'perdido'])

    # Apply trigger filter
    if regla.trigger_tipo == regla.TRIGGER_TIEMPO_CREACION:
        target_start = now - delta - ventana
        target_end = now - delta
        qs = qs.filter(created_at__gte=target_start, created_at__lte=target_end)

    elif regla.trigger_tipo == regla.TRIGGER_TIEMPO_SIN_CAMBIO:
        cutoff = now - delta
        qs = qs.filter(updated_at__lte=cutoff)

    elif regla.trigger_tipo == regla.TRIGGER_TIEMPO_SIN_WA:
        cutoff = now - delta
        qs = qs.filter(
            conversacion_whatsapp__ultimo_mensaje_at__lte=cutoff
        ).exclude(conversacion_whatsapp__isnull=True)

    # Apply conditions
    if regla.condicion_estado:
        qs = qs.filter(estado=regla.condicion_estado)
    if regla.condicion_prioridad:
        qs = qs.filter(prioridad=regla.condicion_prioridad)
    if regla.condicion_origen:
        qs = qs.filter(origen=regla.condicion_origen)

    # Exclude leads already processed by this rule
    ya_procesados = AutomatizacionLog.objects.filter(
        regla=regla
    ).values_list('lead_id', flat=True)
    qs = qs.exclude(pk__in=ya_procesados)

    count = 0
    for lead in qs.select_related('agente', 'conversacion_whatsapp'):
        resultado = _aplicar_accion(regla, lead, now)
        AutomatizacionLog.objects.create(
            regla=regla,
            lead=lead,
            resultado=resultado,
            exitoso=True,
        )
        count += 1
        logger.info('Regla "%s" aplicada al lead #%d: %s', regla.nombre, lead.pk, resultado)

    return count


def _aplicar_accion(regla, lead, now):
    from apps.leads.models import HistorialEstado
    from apps.tasks.models import Tarea

    if regla.accion_tipo == regla.ACCION_CAMBIAR_ESTADO and regla.accion_estado_destino:
        estado_anterior = lead.estado
        lead.estado = regla.accion_estado_destino
        lead.save(update_fields=['estado', 'updated_at'])
        HistorialEstado.objects.create(
            lead=lead,
            estado_anterior=estado_anterior,
            estado_nuevo=lead.estado,
            nota=f'Automatización: {regla.nombre}',
        )
        return f'estado {estado_anterior} → {lead.estado}'

    elif regla.accion_tipo == regla.ACCION_CAMBIAR_PRIORIDAD and regla.accion_prioridad_destino:
        prioridad_anterior = lead.prioridad
        lead.prioridad = regla.accion_prioridad_destino
        lead.save(update_fields=['prioridad', 'updated_at'])
        return f'prioridad {prioridad_anterior} → {lead.prioridad}'

    elif regla.accion_tipo == regla.ACCION_ENVIAR_PLANTILLA_WA and regla.accion_plantilla:
        _enviar_plantilla_wa(regla, lead)
        return f'plantilla "{regla.accion_plantilla.nombre}" enviada a {lead.telefono}'

    elif regla.accion_tipo == regla.ACCION_CREAR_TAREA:
        descripcion = (regla.accion_tarea_descripcion or 'Tarea automática').replace('{lead}', lead.nombre_completo)
        Tarea.objects.create(
            lead=lead,
            agente=lead.agente,
            tipo='llamada',
            descripcion=descripcion,
            fecha_programada=now + timedelta(days=regla.accion_tarea_dias_plazo),
        )
        return f'tarea creada: {descripcion[:50]}'

    return 'sin acción'


def _enviar_plantilla_wa(regla, lead):
    from apps.whatsapp.models import Conversacion, Mensaje
    from apps.whatsapp.sender import send_text_message

    plantilla = regla.accion_plantilla
    if not lead.telefono:
        return

    try:
        text = plantilla.preview()
        result = send_text_message(to=lead.telefono, body=text)
        wam_id = result.get('id', '')
        conv, _ = Conversacion.objects.get_or_create(
            telefono=lead.telefono,
            defaults={'lead': lead, 'nombre_contacto': lead.nombre_completo},
        )
        Mensaje.objects.create(
            conversacion=conv,
            lead=lead,
            direccion=Mensaje.DIR_SALIENTE,
            tipo=Mensaje.TIPO_PLANTILLA,
            contenido=text,
            whatsapp_message_id=wam_id,
            status=Mensaje.STATUS_ENVIADO,
            timestamp=timezone.now(),
        )
    except Exception as e:
        logger.error('Error enviando plantilla WA en automatización: %s', e)
        raise
