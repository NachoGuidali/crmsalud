import logging
from datetime import timedelta

from celery import shared_task
from django.db import models
from django.utils import timezone

from .registry import register_action, ACTION_REGISTRY

logger = logging.getLogger('apps.automations')


# ─── Condición genérica (campo · operador · valor, combinable Y/O) ─────────

def _valor_campo(lead, campo):
    if campo.startswith('cp:'):
        return (lead.datos_extra or {}).get(campo[3:], '')
    return getattr(lead, campo, '') or ''


def _evaluar_operador(actual, operador, esperado):
    from .models import CondicionRegla

    actual = str(actual)
    if operador == CondicionRegla.OP_EQ:
        return actual == esperado
    if operador == CondicionRegla.OP_NEQ:
        return actual != esperado
    if operador == CondicionRegla.OP_CONTAINS:
        return esperado.lower() in actual.lower()
    if operador == CondicionRegla.OP_EMPTY:
        return not actual
    if operador == CondicionRegla.OP_NOT_EMPTY:
        return bool(actual)
    if operador in (CondicionRegla.OP_GT, CondicionRegla.OP_LT):
        try:
            a, e = float(actual), float(esperado)
        except ValueError:
            return False
        return a > e if operador == CondicionRegla.OP_GT else a < e
    return False


def _evaluar_condiciones(regla, lead):
    """Evalúa el set de CondicionRegla de una regla, combinándolas con Y/O en orden."""
    from .models import CondicionRegla

    conds = list(regla.condiciones.all())
    if not conds:
        return True

    resultado = _evaluar_operador(_valor_campo(lead, conds[0].campo), conds[0].operador, conds[0].valor)
    for previa, actual_cond in zip(conds, conds[1:]):
        actual = _evaluar_operador(_valor_campo(lead, actual_cond.campo), actual_cond.operador, actual_cond.valor)
        if previa.join_siguiente == CondicionRegla.JOIN_AND:
            resultado = resultado and actual
        else:
            resultado = resultado or actual
    return resultado


def _delay_a_timedelta(regla):
    from .models import ReglaAutomatizacion
    cantidad = regla.delay_cantidad or 0
    if regla.delay_unidad == ReglaAutomatizacion.DELAY_MINUTOS:
        return timedelta(minutes=cantidad)
    if regla.delay_unidad == ReglaAutomatizacion.DELAY_HORAS:
        return timedelta(hours=cantidad)
    return timedelta(days=cantidad)


# ─── Celery beat: reglas "Automatización" basadas en tiempo (delay / sin actividad) ─

@shared_task
def ejecutar_automatizaciones():
    """Run active time-window Automatización rules. Runs every ~10 min via Celery Beat."""
    from .models import ReglaAutomatizacion

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
        tipo_regla=ReglaAutomatizacion.TIPO_AUTOMATIZACION,
        trigger_tipo__in=[
            ReglaAutomatizacion.TRIGGER_DELAY,
            ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_CAMBIO,
            ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_WA,
        ],
    ).order_by('orden')

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
    """Apply a time-window Automatización rule to all matching leads. Returns leads affected."""
    from .models import AutomatizacionLog, ReglaAutomatizacion
    from apps.leads.models import Lead

    qs = Lead.objects.exclude(estado__in=['afiliado', 'perdido'])
    ventana = timedelta(minutes=15)

    if regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_DELAY:
        delta = _delay_a_timedelta(regla)
        qs = qs.filter(created_at__gte=now - delta - ventana, created_at__lte=now - delta)
    elif regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_CAMBIO:
        delta = timedelta(days=regla.trigger_dias or 0)
        qs = qs.filter(updated_at__lte=now - delta)
    elif regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_WA:
        delta = timedelta(days=regla.trigger_dias or 0)
        qs = qs.filter(
            conversacion_whatsapp__ultimo_mensaje_at__lte=now - delta,
        ).exclude(conversacion_whatsapp__isnull=True)
    else:
        return 0

    # Time-based rules run at most once por lead
    ya_procesados = AutomatizacionLog.objects.filter(regla=regla).values_list('lead_id', flat=True)
    qs = qs.exclude(pk__in=ya_procesados)

    count = 0
    for lead in qs.select_related('agente', 'conversacion_whatsapp'):
        if not _evaluar_condiciones(regla, lead):
            continue
        resultado = _dispatch_action(regla, lead, now)
        AutomatizacionLog.objects.create(regla=regla, lead=lead, resultado=resultado, exitoso=True)
        count += 1
        logger.info('Regla "%s" → lead #%d: %s', regla.nombre, lead.pk, resultado)

    return count


# ─── Celery beat: reglas "Automatización" — campo de fecha = referencia ± offset ───

@shared_task
def ejecutar_automatizaciones_fecha_campo():
    """Run active 'campo de fecha = referencia' Automatización rules. Runs once a day."""
    from .models import ReglaAutomatizacion

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
        tipo_regla=ReglaAutomatizacion.TIPO_AUTOMATIZACION,
        trigger_tipo=ReglaAutomatizacion.TRIGGER_FECHA_CAMPO,
    ).order_by('orden')

    now = timezone.now()
    total = 0
    for regla in reglas:
        try:
            total += _ejecutar_regla_fecha_campo(regla, now)
        except Exception as e:
            logger.error('Error ejecutando regla fecha-campo "%s": %s', regla.nombre, e)

    logger.info('Automatizaciones fecha-campo: %d acciones ejecutadas', total)
    return f'{total} acciones ejecutadas'


def _ejecutar_regla_fecha_campo(regla, now):
    """
    Match leads whose `fecha_campo_objetivo` (mes/día) coincide con hoy ± offset.
    Dedup diario vía AutomatizacionLog — permite que la regla vuelva a dispararse
    el año siguiente (útil para recordatorios anuales tipo cumpleaños).
    """
    from .models import AutomatizacionLog, ReglaAutomatizacion
    from apps.leads.models import Lead

    campo = regla.fecha_campo_objetivo
    if not campo:
        return 0

    hoy_local = timezone.localtime(now)
    offset = timedelta(days=regla.fecha_campo_offset_dias or 0)
    if regla.fecha_campo_offset_signo == ReglaAutomatizacion.OFFSET_ANTES:
        objetivo = (hoy_local + offset).date()
    else:
        objetivo = (hoy_local - offset).date()

    qs = Lead.objects.exclude(estado__in=['afiliado', 'perdido']).filter(**{
        f'{campo}__month': objetivo.month,
        f'{campo}__day': objetivo.day,
    })

    ya_procesados = AutomatizacionLog.objects.filter(
        regla=regla, ejecutado_at__date=timezone.localtime(now).date(),
    ).values_list('lead_id', flat=True)
    qs = qs.exclude(pk__in=ya_procesados)

    count = 0
    for lead in qs.select_related('agente', 'conversacion_whatsapp'):
        if not _evaluar_condiciones(regla, lead):
            continue
        resultado = _dispatch_action(regla, lead, now)
        AutomatizacionLog.objects.create(regla=regla, lead=lead, resultado=resultado, exitoso=True)
        count += 1
        logger.info('Regla fecha-campo "%s" → lead #%d: %s', regla.nombre, lead.pk, resultado)

    return count


# ─── Síncrono: reglas "Automatización → Inmediatamente" ────────────────────

def ejecutar_automatizaciones_inmediatas(lead_id):
    """
    Fire 'Automatización → Inmediatamente' rules for a lead right after it's saved.
    Runs at most once por lead por regla (deduped vía AutomatizacionLog), igual que
    el resto de reglas de Automatización — se ejecuta apenas la condición se cumple.
    """
    from .models import ReglaAutomatizacion, AutomatizacionLog
    from apps.leads.models import Lead

    try:
        lead = Lead.objects.select_related('agente', 'conversacion_whatsapp').get(pk=lead_id)
    except Lead.DoesNotExist:
        return

    ya_procesadas = AutomatizacionLog.objects.filter(
        regla__tipo_regla=ReglaAutomatizacion.TIPO_AUTOMATIZACION,
        regla__trigger_tipo=ReglaAutomatizacion.TRIGGER_INMEDIATO,
        lead=lead,
    ).values_list('regla_id', flat=True)

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
        tipo_regla=ReglaAutomatizacion.TIPO_AUTOMATIZACION,
        trigger_tipo=ReglaAutomatizacion.TRIGGER_INMEDIATO,
    ).exclude(pk__in=ya_procesadas).order_by('orden')

    now = timezone.now()
    for regla in reglas:
        if not _evaluar_condiciones(regla, lead):
            continue
        lead_ref = lead.pk
        log = AutomatizacionLog.objects.create(regla=regla, lead=lead, resultado='ejecutando...', exitoso=True)
        try:
            resultado = _dispatch_action(regla, lead, now)
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=resultado)
            logger.info('Regla inmediata "%s" → lead #%s: %s', regla.nombre, lead_ref, resultado)
        except Exception as e:
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=str(e)[:500], exitoso=False)
            logger.error('Error en regla inmediata "%s" lead #%s: %s', regla.nombre, lead_ref, e)


# ─── Síncrono: reglas "Disparador → Al crear el lead" ──────────────────────

def ejecutar_disparadores_creacion(lead_id):
    """Fire 'Disparador → Al crear el lead' rules right after a lead is created."""
    from .models import ReglaAutomatizacion, AutomatizacionLog
    from apps.leads.models import Lead

    try:
        lead = Lead.objects.select_related('agente', 'conversacion_whatsapp').get(pk=lead_id)
    except Lead.DoesNotExist:
        return

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True,
        tipo_regla=ReglaAutomatizacion.TIPO_DISPARADOR,
        trigger_tipo=ReglaAutomatizacion.TRIGGER_CREADO,
    ).order_by('orden')

    now = timezone.now()
    for regla in reglas:
        if not _evaluar_condiciones(regla, lead):
            continue
        lead_ref = lead.pk
        log = AutomatizacionLog.objects.create(
            regla=regla, lead=lead, resultado='ejecutando...', exitoso=True, evento='lead creado',
        )
        try:
            resultado = _dispatch_action(regla, lead, now)
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=resultado)
            logger.info('Regla creación "%s" → lead #%s: %s', regla.nombre, lead_ref, resultado)
        except Exception as e:
            AutomatizacionLog.objects.filter(pk=log.pk).update(resultado=str(e)[:500], exitoso=False)
            logger.error('Error en regla creación "%s" lead #%s: %s', regla.nombre, lead_ref, e)


# ─── Síncrono: reglas "Disparador" basadas en cambio de campo ──────────────

def ejecutar_automatizaciones_por_evento(lead_id, campo, valor_anterior, valor_nuevo):
    """
    Fire all "Disparador" rules that match a field change on a lead
    (campo_cambia / campo_igual_a / responsable_cambia).
    Called synchronously from the Lead post_save signal — no Celery.
    """
    from .models import ReglaAutomatizacion, AutomatizacionLog
    from apps.leads.models import Lead

    try:
        lead = Lead.objects.select_related('agente', 'conversacion_whatsapp').get(pk=lead_id)
    except Lead.DoesNotExist:
        return

    coincide = (
        models.Q(trigger_tipo=ReglaAutomatizacion.TRIGGER_CAMPO_CAMBIA, trigger_campo=campo)
        | models.Q(trigger_tipo=ReglaAutomatizacion.TRIGGER_CAMPO_IGUAL_A, trigger_campo=campo,
                   trigger_valor_nuevo=valor_nuevo)
    )
    if campo == 'agente':
        coincide |= models.Q(trigger_tipo=ReglaAutomatizacion.TRIGGER_RESPONSABLE_CAMBIA)

    reglas = ReglaAutomatizacion.objects.filter(
        activa=True, tipo_regla=ReglaAutomatizacion.TIPO_DISPARADOR,
    ).filter(coincide).order_by('orden')

    evento_desc = f'{campo}:{valor_anterior}→{valor_nuevo}'
    now = timezone.now()

    for regla in reglas:
        if regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_CAMPO_IGUAL_A:
            if regla.trigger_valor_anterior and regla.trigger_valor_anterior != valor_anterior:
                continue
        if not _evaluar_condiciones(regla, lead):
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

    import re
    text = plantilla.preview_for_contact(lead) if re.search(r'\{\{[a-zA-Z_]', plantilla.cuerpo) else plantilla.preview()
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
