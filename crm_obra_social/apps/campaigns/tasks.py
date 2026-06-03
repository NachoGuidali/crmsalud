import logging
import time

from celery import shared_task

logger = logging.getLogger('apps.campaigns')

RATE_LIMIT_PER_MINUTE = 800  # Safely under Meta's 1000/min limit

# Works for both Lead (plan_interes) and Cliente (plan)
CONTACT_FIELD_MAP = {
    'nombre_completo': lambda obj: getattr(obj, 'nombre_completo', '') or '',
    'email':           lambda obj: getattr(obj, 'email', '') or '',
    'plan':            lambda obj: str(getattr(obj, 'plan_interes', None) or getattr(obj, 'plan', None) or ''),
    'localidad':       lambda obj: getattr(obj, 'localidad', '') or '',
    'provincia':       lambda obj: getattr(obj, 'provincia', '') or '',
    'telefono':        lambda obj: getattr(obj, 'telefono', '') or '',
}


def _build_variables_for_contact(contact, variables_mapping: list) -> list:
    """Resolve template variable values for a Lead or Cliente."""
    vals = []
    for mapping in variables_mapping:
        tipo = mapping.get('tipo', 'fijo')
        valor = mapping.get('valor', '')
        if tipo == 'campo':
            vals.append(CONTACT_FIELD_MAP[valor](contact) if valor in CONTACT_FIELD_MAP else '')
        elif tipo == 'extra':
            vals.append(str((getattr(contact, 'datos_extra', {}) or {}).get(valor, '')))
        else:
            vals.append(valor)
    return vals


@shared_task(bind=True)
def ejecutar_campana(self, campana_id: int):
    """Send bulk messages for a campaign using Evolution API."""
    from apps.leads.models import Lead
    from apps.clientes.models import Cliente
    from .models import Campana, CampanaLog
    from apps.whatsapp.sender import send_text_message

    campana = Campana.objects.select_related('plantilla').get(pk=campana_id)
    campana.status = Campana.STATUS_EN_EJECUCION
    campana.save(update_fields=['status'])

    recipients = campana.get_recipients()
    campana.total_destinatarios = len(recipients)
    campana.save(update_fields=['total_destinatarios'])

    plantilla = campana.plantilla
    variables_mapping = campana.variables_mapping or []
    enviados = 0
    errores = 0
    interval = 60.0 / RATE_LIMIT_PER_MINUTE

    import re
    uses_named_vars = bool(re.search(r'\{\{[a-zA-Z_]', plantilla.cuerpo))

    for contact in recipients:
        is_cliente = isinstance(contact, Cliente)
        try:
            if uses_named_vars:
                text = plantilla.preview_for_contact(contact)
            else:
                variables_vals = _build_variables_for_contact(contact, variables_mapping)
                text = plantilla.preview(variables_vals) if variables_vals else plantilla.cuerpo
            result = send_text_message(to=contact.telefono, body=text)
            wam_id = result.get('id', '')
            CampanaLog.objects.create(
                campana=campana,
                lead=None if is_cliente else contact,
                cliente=contact if is_cliente else None,
                telefono=contact.telefono,
                nombre_contacto=contact.nombre_completo,
                status=CampanaLog.STATUS_ENVIADO,
                whatsapp_message_id=wam_id,
            )
            enviados += 1
            logger.info('Campaign %d: sent to %s', campana_id, contact.telefono)
        except Exception as e:
            CampanaLog.objects.create(
                campana=campana,
                lead=None if is_cliente else contact,
                cliente=contact if is_cliente else None,
                telefono=contact.telefono,
                nombre_contacto=contact.nombre_completo,
                status=CampanaLog.STATUS_ERROR,
                error_detalle=str(e),
            )
            errores += 1
            logger.error('Campaign %d: error sending to %s: %s', campana_id, contact.telefono, e)
        time.sleep(interval)

    campana.enviados = enviados
    campana.errores = errores
    campana.status = Campana.STATUS_COMPLETADA
    campana.save(update_fields=['enviados', 'errores', 'status', 'updated_at'])
    return f'Campaña {campana_id}: {enviados} enviados, {errores} errores.'


@shared_task
def lanzar_campanas_programadas():
    """Launch scheduled campaigns that are due. Runs every 5 minutes via Celery Beat."""
    from .models import Campana
    from django.utils import timezone
    now = timezone.now()
    campanas = Campana.objects.filter(status=Campana.STATUS_PROGRAMADA, fecha_programada__lte=now)
    for c in campanas:
        ejecutar_campana.delay(c.pk)
        logger.info('Launched scheduled campaign %d: %s', c.pk, c.nombre)
