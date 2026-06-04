import logging

from celery import shared_task
from django.db.models import Count, Q
from django.utils import timezone

from utils.phone import normalize_ar_phone, ar_phone_variants

logger = logging.getLogger('apps.whatsapp')


def _assign_agent(conv):
    """
    Assign the available agent with the lowest open conversation load.
    Returns the assigned User, or None if no agents are available.
    Priority: ROLE_AGENTE first, ROLE_SUPERVISOR as fallback.
    """
    from apps.users.models import User
    from .models import Conversacion

    active_states = [Conversacion.ESTADO_PENDIENTE, Conversacion.ESTADO_ABIERTA]

    for roles in ([User.ROLE_AGENTE], [User.ROLE_SUPERVISOR, User.ROLE_SUPERADMIN]):
        agent = (
            User.objects
            .filter(is_active=True, disponible=True, role__in=roles)
            .annotate(carga=Count(
                'conversaciones',
                filter=Q(conversaciones__estado__in=active_states),
            ))
            .order_by('carga', 'id')
            .first()
        )
        if agent:
            logger.info('Auto-assigned conv %s to %s (carga=%s)', conv.pk, agent.username,
                        agent.carga if hasattr(agent, 'carga') else '?')
            return agent

    logger.warning('No available agents for conv %s — left unassigned', conv.pk)
    return None


def _redistribute_conversations(agent):
    """
    Redistribute open/pending conversations from a now-unavailable agent.
    Called when an agent is deactivated or marks themselves unavailable.
    """
    from .models import Conversacion
    convs = Conversacion.objects.filter(
        agente=agent,
        estado__in=[Conversacion.ESTADO_PENDIENTE, Conversacion.ESTADO_ABIERTA],
    )
    reassigned = 0
    for conv in convs:
        conv.agente = None  # clear first so _assign_agent doesn't count it
        new_agent = _assign_agent(conv)
        conv.agente = new_agent
        conv.save(update_fields=['agente'])
        reassigned += 1
    logger.info('Redistributed %d conversations from %s', reassigned, agent.username)


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
                estado=Conversacion.ESTADO_PENDIENTE,
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

        # Sync agente from lead; auto-assign if still None
        if conv.lead and conv.lead.agente_id and not conv.agente_id:
            conv.agente_id = conv.lead.agente_id
        elif not conv.agente_id:
            assigned = _assign_agent(conv)
            if assigned:
                conv.agente = assigned

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

        msg_type     = message_data.get('type', Mensaje.TIPO_TEXTO)
        message_id   = message_data.get('message_id', '')
        media_url    = message_data.get('media_url', '')
        media_mime   = message_data.get('media_mime', '')
        media_filename = message_data.get('media_filename', '')

        # Decrypt and download media via Evolution API (WhatsApp encrypts all media)
        if msg_type in (Mensaje.TIPO_IMAGEN, Mensaje.TIPO_DOCUMENTO,
                        Mensaje.TIPO_AUDIO, Mensaje.TIPO_VIDEO) and message_id:
            try:
                from .sender import download_and_save_media
                local_url, resolved_mime = download_and_save_media(
                    message_id, conv.pk, filename=media_filename,
                )
                if local_url:
                    media_url = local_url
                if resolved_mime:
                    media_mime = resolved_mime
            except Exception as dl_err:
                logger.warning('Media download failed for %s: %s', message_id, dl_err)

        mensaje = Mensaje.objects.create(
            conversacion=conv,
            lead=conv.lead,
            whatsapp_message_id=message_id,
            direccion=Mensaje.DIR_ENTRANTE,
            tipo=msg_type,
            contenido=message_data.get('content', ''),
            media_url=media_url,
            media_mime=media_mime,
            media_filename=media_filename,
            status=Mensaje.STATUS_ENTREGADO,
            timestamp=message_data['timestamp'],
        )

        # Auto-save incoming media to lead's document list
        if (media_url and conv.lead
                and msg_type in (Mensaje.TIPO_IMAGEN, Mensaje.TIPO_DOCUMENTO,
                                 Mensaje.TIPO_VIDEO, Mensaje.TIPO_AUDIO)):
            try:
                from apps.leads.models import Documento
                tipo_label = {
                    Mensaje.TIPO_IMAGEN: 'Imagen',
                    Mensaje.TIPO_DOCUMENTO: 'Documento',
                    Mensaje.TIPO_VIDEO: 'Video',
                    Mensaje.TIPO_AUDIO: 'Audio',
                }.get(msg_type, 'Archivo')
                contact_name = (message_data.get('contact_name', '')
                                or conv.nombre_contacto
                                or conv.telefono)
                doc_nombre = media_filename or f'{tipo_label} de {contact_name}'
                Documento.objects.create(
                    lead=conv.lead,
                    nombre=f'WA — {doc_nombre}',
                    tipo=Documento.TIPO_OTRO,
                    url_externa=media_url,
                    fuente=Documento.FUENTE_WHATSAPP,
                )
            except Exception as doc_err:
                logger.warning('Could not create Documento for incoming media: %s', doc_err)

        # Trigger bot auto-response rules (only if CRM bot is active for this conversation)
        if conv.bot_crm_activo:
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
