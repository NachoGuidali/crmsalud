import logging
from datetime import timedelta

from celery import shared_task
from django.db import models
from django.utils import timezone

from .registry import register_action, ACTION_REGISTRY

logger = logging.getLogger('apps.automations')


# ─── Celery beat task (time-based) ─────────────────────────────────────────

@shared_task
def ejecutar_automatizaciones():
    """Run all active time-based automation rules. Runs every hour via Celery Beat."""
    from .models import ReglaAutomatizacion

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
    ).exclude(trigger_tipo=ReglaAutomatizacion.TRIGGER_ESTADO_CAMBIO).order_by('orden')

    now = timezone.now()
    total = 0
    for regla in reglas:
        try:
            total += _ejecutar_regla(regla, now)
        except Exception as e:
            logger.error('Error ejecutando regla "%s": %s', regla.nombre, e)

    logger.info('Automatizaciones time-based: %d acciones ejecutadas', total)
    return f'{total} acciones ejecutadas'


def _ejecutar_regla(regla, now):
    """Apply a time-based rule to all matching leads. Returns count of leads affected."""
    from .models import AutomatizacionLog
    from apps.leads.models import Lead

    delta = timedelta(days=regla.trigger_dias or 0)
    ventana = timedelta(hours=2)

    qs = Lead.objects.exclude(estado__in=['afiliado', 'perdido'])

    if regla.trigger_tipo == regla.TRIGGER_TIEMPO_CREACION:
        target_start = now - delta - ventana
        target_end   = now - delta
        qs = qs.filter(created_at__gte=target_start, created_at__lte=target_end)
    elif regla.trigger_tipo == regla.TRIGGER_TIEMPO_SIN_CAMBIO:
        qs = qs.filter(updated_at__lte=now - delta)
    elif regla.trigger_tipo == regla.TRIGGER_TIEMPO_SIN_WA:
        qs = qs.filter(
            conversacion_whatsapp__ultimo_mensaje_at__lte=now - delta,
        ).exclude(conversacion_whatsapp__isnull=True)

    if regla.condicion_estado:
        qs = qs.filter(estado=regla.condicion_estado)
    if regla.condicion_prioridad:
        qs = qs.filter(prioridad=regla.condicion_prioridad)
    if regla.condicion_origen:
        qs = qs.filter(origen=regla.condicion_origen)

    # Time-based rules run at most once per lead
    ya_procesados = AutomatizacionLog.objects.filter(regla=regla).values_list('lead_id', flat=True)
    qs = qs.exclude(pk__in=ya_procesados)

    count = 0
    for lead in qs.select_related('agente', 'conversacion_whatsapp'):
        resultado = _dispatch_action(regla, lead, now)
        AutomatizacionLog.objects.create(regla=regla, lead=lead, resultado=resultado, exitoso=True)
        count += 1
        logger.info('Regla "%s" → lead #%d: %s', regla.nombre, lead.pk, resultado)

    return count


# ─── Event-based execution (called synchronously from signal) ──────────────

def ejecutar_automatizaciones_por_evento(lead_id, campo, valor_anterior, valor_nuevo):
    """
    Fire all event-based rules that match the given field change on a lead.
    Called synchronously from the Lead post_save signal — no Celery.
    """
    from .models import ReglaAutomatizacion, AutomatizacionLog
    from apps.leads.models import Lead

    try:
        lead = Lead.objects.select_related('agente', 'conversacion_whatsapp').get(pk=lead_id)
    except Lead.DoesNotExist:
        return

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
        trigger_tipo=ReglaAutomatizacion.TRIGGER_ESTADO_CAMBIO,
        trigger_campo=campo,
        trigger_valor_nuevo=valor_nuevo,
    ).filter(
        models.Q(trigger_valor_anterior='') | models.Q(trigger_valor_anterior=valor_anterior)
    ).order_by('orden')

    # Apply optional conditions
    if reglas:
        if any(r.condicion_estado for r in reglas):
            pass  # evaluated per-rule below

    evento_desc = f'{campo}:{valor_anterior}→{valor_nuevo}'
    now = timezone.now()

    for regla in reglas:
        if regla.condicion_estado and lead.estado != regla.condicion_estado:
            continue
        if regla.condicion_prioridad and lead.prioridad != regla.condicion_prioridad:
            continue
        if regla.condicion_origen and lead.origen != regla.condicion_origen:
            continue

        # Create log BEFORE running action — action may delete the lead (convertir_cliente),
        # which sets log.lead → NULL via SET_NULL, but the row survives.
        # Use queryset.update() to persist result — log.save() would fail if lead.pk
        # became None after deletion (Django's "unsaved related object" guard).
        log = AutomatizacionLog.objects.create(
            regla=regla, lead=lead,
            resultado='ejecutando...', exitoso=True, evento=evento_desc,
        )
        lead_ref = lead.pk  # capture before possible deletion
        try:
            resultado = _dispatch_action(regla, lead, now)
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=resultado)
            logger.info('Regla evento "%s" → lead #%s [%s]: %s', regla.nombre, lead_ref, evento_desc, resultado)
        except Exception as e:
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=str(e)[:500], exitoso=False)
            logger.error('Error en regla evento "%s" lead #%s: %s', regla.nombre, lead_ref, e)


# ─── Action dispatcher ──────────────────────────────────────────────────────

def _dispatch_action(regla, lead, now):
    handler = ACTION_REGISTRY.get(regla.accion_tipo)
    if handler:
        return handler(regla, lead, now)
    return 'sin acción registrada'


# ─── Action implementations (registered via decorator) ─────────────────────

@register_action('cambiar_estado')
def _accion_cambiar_estado(regla, lead, now):
    from apps.leads.models import HistorialEstado
    if not regla.accion_estado_destino:
        return 'sin estado destino configurado'
    estado_anterior = lead.estado
    lead.estado = regla.accion_estado_destino
    lead._skip_automation = True  # prevent recursive signal
    lead.save(update_fields=['estado', 'updated_at'])
    HistorialEstado.objects.create(
        lead=lead,
        estado_anterior=estado_anterior,
        estado_nuevo=lead.estado,
        nota=f'Automatización: {regla.nombre}',
    )
    return f'estado {estado_anterior} → {lead.estado}'


@register_action('cambiar_prioridad')
def _accion_cambiar_prioridad(regla, lead, now):
    if not regla.accion_prioridad_destino:
        return 'sin prioridad destino configurada'
    anterior = lead.prioridad
    lead.prioridad = regla.accion_prioridad_destino
    lead._skip_automation = True
    lead.save(update_fields=['prioridad', 'updated_at'])
    return f'prioridad {anterior} → {lead.prioridad}'


@register_action('enviar_plantilla_wa')
def _accion_enviar_plantilla_wa(regla, lead, now):
    from apps.whatsapp.models import Conversacion, Mensaje
    from apps.whatsapp.sender import send_text_message

    plantilla = regla.accion_plantilla
    if not plantilla or not lead.telefono:
        return 'plantilla o teléfono no disponible'

    text = plantilla.preview()
    result = send_text_message(to=lead.telefono, body=text)
    wam_id = result.get('id', '')
    conv, _ = Conversacion.objects.get_or_create(
        telefono=lead.telefono,
        defaults={'lead': lead, 'nombre_contacto': lead.nombre_completo},
    )
    Mensaje.objects.create(
        conversacion=conv, lead=lead,
        direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_PLANTILLA,
        contenido=text, whatsapp_message_id=wam_id,
        status=Mensaje.STATUS_ENVIADO, timestamp=now,
    )
    return f'plantilla "{plantilla.nombre}" enviada a {lead.telefono}'


@register_action('crear_tarea')
def _accion_crear_tarea(regla, lead, now):
    from apps.tasks.models import Tarea
    descripcion = (regla.accion_tarea_descripcion or 'Tarea automática').replace('{lead}', lead.nombre_completo)
    Tarea.objects.create(
        lead=lead,
        agente=lead.agente,
        tipo='llamada',
        descripcion=descripcion,
        fecha_programada=now + timedelta(days=regla.accion_tarea_dias_plazo),
    )
    return f'tarea creada: {descripcion[:50]}'


@register_action('enviar_mensaje_wa')
def _accion_enviar_mensaje_wa(regla, lead, now):
    from apps.whatsapp.models import Conversacion, Mensaje
    from apps.whatsapp.sender import send_text_message

    if not regla.accion_mensaje_texto or not lead.telefono:
        return 'mensaje o teléfono no disponible'

    texto = regla.accion_mensaje_texto.replace('{lead}', lead.nombre_completo) \
                                      .replace('{estado}', lead.estado) \
                                      .replace('{telefono}', lead.telefono)
    result = send_text_message(to=lead.telefono, body=texto)
    wam_id = result.get('id', '')
    conv, _ = Conversacion.objects.get_or_create(
        telefono=lead.telefono,
        defaults={'lead': lead, 'nombre_contacto': lead.nombre_completo},
    )
    Mensaje.objects.create(
        conversacion=conv, lead=lead,
        direccion=Mensaje.DIR_SALIENTE, tipo=Mensaje.TIPO_TEXTO,
        contenido=texto, whatsapp_message_id=wam_id,
        status=Mensaje.STATUS_ENVIADO, timestamp=now,
    )
    return f'mensaje WA enviado a {lead.telefono}'


@register_action('asignar_agente')
def _accion_asignar_agente(regla, lead, now):
    if not regla.accion_agente_id:
        return 'sin agente configurado'
    anterior = str(lead.agente) if lead.agente else 'ninguno'
    lead.agente = regla.accion_agente
    lead._skip_automation = True
    lead.save(update_fields=['agente', 'updated_at'])
    return f'agente asignado: {anterior} → {regla.accion_agente}'


@register_action('convertir_cliente')
def _accion_convertir_cliente(regla, lead, now):
    from apps.clientes.models import Cliente

    if Cliente.objects.filter(dni=lead.dni).exists():
        return f'cliente con DNI {lead.dni} ya existe, conversión omitida'

    cliente = Cliente.objects.create(
        nombre_completo=lead.nombre_completo,
        dni=lead.dni,
        fecha_nacimiento=lead.fecha_nacimiento,
        telefono=lead.telefono,
        email=lead.email,
        localidad=lead.localidad,
        provincia=lead.provincia,
        plan=lead.plan_interes,
        grupo_familiar=lead.grupo_familiar,
        agente=lead.agente,
        notas=lead.notas,
        datos_extra=lead.datos_extra or {},
    )
    lead._skip_automation = True
    lead.delete()  # log FK → SET_NULL so it survives the deletion
    return f'lead convertido a cliente #{cliente.pk}: {cliente.nombre_completo}'


@register_action('llamar_webhook')
def _accion_llamar_webhook(regla, lead, now):
    import requests
    if not regla.accion_webhook_url:
        return 'sin URL configurada'

    payload = {
        'lead_id':        lead.pk,
        'nombre':         lead.nombre_completo,
        'telefono':       lead.telefono,
        'email':          lead.email,
        'estado':         lead.estado,
        'prioridad':      lead.prioridad,
        'origen':         lead.origen,
        'datos_extra':    lead.datos_extra,
        'regla_nombre':   regla.nombre,
        'timestamp':      now.isoformat(),
    }
    try:
        resp = requests.post(regla.accion_webhook_url, json=payload, timeout=10)
        return f'webhook llamado → HTTP {resp.status_code}'
    except Exception as e:
        logger.warning('Webhook error en regla "%s": %s', regla.nombre, e)
        raise
