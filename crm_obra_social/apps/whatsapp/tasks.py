import logging

from celery import shared_task
from django.utils import timezone

from utils.phone import normalize_ar_phone, ar_phone_variants

logger = logging.getLogger('apps.whatsapp')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_incoming_message(self, message_data: dict):
    """Process a single incoming WhatsApp message asynchronously."""
    from apps.leads.models import Lead, HistorialEstado
    from .models import Conversacion, Mensaje

    phone = message_data.get('from_phone', '')
    if not phone:
        return

    phone = normalize_ar_phone(phone)

    try:
        # Try to find existing conversation — check both +549X and +54X variants
        conv = None
        for variant in ar_phone_variants(phone):
            conv = Conversacion.objects.filter(telefono=variant).first()
            if conv:
                break

        if conv is None:
            conv = Conversacion.objects.create(
                telefono=phone,
                nombre_contacto=message_data.get('contact_name', ''),
            )
        elif message_data.get('contact_name') and not conv.nombre_contacto:
            conv.nombre_contacto = message_data['contact_name']
            conv.save(update_fields=['nombre_contacto'])

        if not conv.lead:
            lead = Lead.objects.filter(telefono__in=ar_phone_variants(phone)).first()
            if not lead:
                lead = Lead.objects.create(
                    nombre_completo=message_data.get('contact_name') or f'WhatsApp {phone}',
                    dni='0000000',
                    telefono=phone,
                    origen=Lead.ORIGEN_WHATSAPP,
                    estado=Lead.ESTADO_NUEVO,
                )
                HistorialEstado.objects.create(
                    lead=lead,
                    estado_nuevo=lead.estado,
                    nota='Lead creado automáticamente desde WhatsApp.',
                )
            conv.lead = lead

        # Sync conversation agente from lead agente
        if conv.lead and conv.lead.agente_id and not conv.agente_id:
            conv.agente_id = conv.lead.agente_id

        conv.ultimo_mensaje_at = message_data['timestamp']
        conv.mensajes_no_leidos += 1
        conv.save()

        # Auto-change lead status NUEVO → CONTACTADO on first incoming message
        if conv.lead and conv.lead.estado == Lead.ESTADO_NUEVO:
            Lead.objects.filter(pk=conv.lead.pk).update(estado=Lead.ESTADO_CONTACTADO)
            HistorialEstado.objects.create(
                lead=conv.lead,
                estado_anterior=Lead.ESTADO_NUEVO,
                estado_nuevo=Lead.ESTADO_CONTACTADO,
                nota='Cambio automático al recibir mensaje WhatsApp.',
            )

        msg_type = message_data.get('type', Mensaje.TIPO_TEXTO)

        mensaje = Mensaje.objects.create(
            conversacion=conv,
            lead=conv.lead,
            whatsapp_message_id=message_data.get('message_id', ''),
            direccion=Mensaje.DIR_ENTRANTE,
            tipo=msg_type,
            contenido=message_data.get('content', ''),
            media_url=message_data.get('media_url', ''),
            status=Mensaje.STATUS_ENTREGADO,
            timestamp=message_data['timestamp'],
        )

        # Trigger bot auto-response rules
        _apply_bot_rules(conv, msg_type, message_data.get('content', ''))

    except Exception as exc:
        logger.exception('Error processing incoming message from %s: %s', phone, exc)
        raise self.retry(exc=exc)


def _apply_bot_rules(conv, msg_type: str, message_text: str):
    """Check and execute matching bot response rules."""
    from .models import BotRespuesta, LogBotRespuesta, Mensaje
    from .sender import send_text_message, send_interactive_message
    from apps.leads.models import HistorialEstado

    reglas = BotRespuesta.objects.filter(activa=True).order_by('orden')
    if not reglas.exists():
        return

    is_first_message = conv.mensajes.filter(direccion=Mensaje.DIR_ENTRANTE).count() == 1

    for regla in reglas:
        matched = False
        if regla.trigger_tipo == BotRespuesta.TRIGGER_PRIMER_MENSAJE and is_first_message:
            matched = True
        elif regla.trigger_tipo == BotRespuesta.TRIGGER_PALABRA_CLAVE and msg_type == 'text':
            matched = regla.matches(message_text)

        if not matched:
            continue

        if regla.solo_si_sin_agente and conv.agente_id:
            continue

        if regla.solo_primera_vez:
            if LogBotRespuesta.objects.filter(conversacion=conv, regla=regla).exists():
                continue

        try:
            wam_id = ''
            contenido_log = ''

            if regla.respuesta_tipo == BotRespuesta.RESPUESTA_TEXTO and regla.respuesta_texto:
                result = send_text_message(conv.telefono, regla.respuesta_texto)
                wam_id = result.get('id', '')
                contenido_log = regla.respuesta_texto

            elif regla.respuesta_tipo == BotRespuesta.RESPUESTA_PLANTILLA and regla.respuesta_plantilla:
                plantilla = regla.respuesta_plantilla
                text = plantilla.preview()
                result = send_text_message(conv.telefono, text)
                wam_id = result.get('id', '')
                contenido_log = text

            elif regla.respuesta_tipo == BotRespuesta.RESPUESTA_INTERACTIVO and regla.respuesta_interactivo_body:
                buttons = regla.respuesta_interactivo_botones or []
                result = send_interactive_message(conv.telefono, regla.respuesta_interactivo_body, buttons)
                wam_id = result.get('id', '')
                contenido_log = regla.respuesta_interactivo_body + ' | ' + ' | '.join(
                    b.get('title', '') for b in buttons
                )

            if contenido_log:
                Mensaje.objects.create(
                    conversacion=conv,
                    lead=conv.lead,
                    direccion=Mensaje.DIR_SALIENTE,
                    tipo=Mensaje.TIPO_TEXTO if regla.respuesta_tipo == BotRespuesta.RESPUESTA_TEXTO else (
                        Mensaje.TIPO_PLANTILLA if regla.respuesta_tipo == BotRespuesta.RESPUESTA_PLANTILLA
                        else Mensaje.TIPO_INTERACTIVO
                    ),
                    contenido=contenido_log,
                    whatsapp_message_id=wam_id,
                    status=Mensaje.STATUS_ENVIADO,
                    timestamp=timezone.now(),
                )

            if conv.lead:
                lead = conv.lead
                updated = []
                if regla.accion_estado and lead.estado != regla.accion_estado:
                    estado_ant = lead.estado
                    lead.estado = regla.accion_estado
                    updated.append('estado')
                    HistorialEstado.objects.create(
                        lead=lead,
                        estado_anterior=estado_ant,
                        estado_nuevo=lead.estado,
                        nota=f'Bot: {regla.nombre}',
                    )
                if regla.accion_prioridad and lead.prioridad != regla.accion_prioridad:
                    lead.prioridad = regla.accion_prioridad
                    updated.append('prioridad')
                if updated:
                    lead.save(update_fields=updated + ['updated_at'])

            if regla.solo_primera_vez:
                LogBotRespuesta.objects.get_or_create(conversacion=conv, regla=regla)

            logger.info('Bot regla "%s" aplicada a conversación %d', regla.nombre, conv.pk)
            break  # First matching rule wins

        except Exception as e:
            logger.error('Bot error en regla "%s": %s', regla.nombre, e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message_task(self, mensaje_id: int):
    """Send a queued outgoing text message."""
    from .models import Mensaje
    from .sender import send_text_message

    try:
        mensaje = Mensaje.objects.select_related('conversacion').get(pk=mensaje_id)
        result = send_text_message(mensaje.conversacion.telefono, mensaje.contenido)
        wam_id = result.get('id', '')
        Mensaje.objects.filter(pk=mensaje_id).update(
            whatsapp_message_id=wam_id,
            status=Mensaje.STATUS_ENVIADO,
        )
    except Exception as exc:
        logger.exception('Error sending message %s: %s', mensaje_id, exc)
        Mensaje.objects.filter(pk=mensaje_id).update(
            status=Mensaje.STATUS_FALLIDO,
            error_detalle=str(exc),
        )
        raise self.retry(exc=exc)
