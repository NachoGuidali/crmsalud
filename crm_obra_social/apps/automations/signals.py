import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

logger = logging.getLogger('apps.automations')

WATCHED_FIELDS = ('estado', 'prioridad', 'agente')


@receiver(pre_save, sender='leads.Lead')
def lead_pre_save(sender, instance, **kwargs):
    """Capture current field values before save so post_save can detect changes."""
    if not instance.pk:
        instance._pre_save_values = {}
        return
    try:
        old = sender.objects.only(*WATCHED_FIELDS).get(pk=instance.pk)
        instance._pre_save_values = {f: getattr(old, f) for f in WATCHED_FIELDS}
    except sender.DoesNotExist:
        instance._pre_save_values = {}


@receiver(post_save, sender='leads.Lead')
def lead_post_save(sender, instance, created, **kwargs):
    """
    Fire 'Disparador' rules (al crear / campo cambia / responsable cambia) and
    'Automatización → Inmediatamente' rules synchronously after a lead is saved.
    """
    if getattr(instance, '_skip_automation', False):
        return

    from apps.automations.tasks import (
        ejecutar_automatizaciones_por_evento,
        ejecutar_automatizaciones_inmediatas,
        ejecutar_disparadores_creacion,
    )

    lead_pk = instance.pk  # capture before any action deletes the lead

    if created:
        try:
            ejecutar_disparadores_creacion(lead_id=lead_pk)
        except Exception as e:
            logger.error('Error procesando disparador "Al crear" lead #%s: %s', lead_pk, e)
    else:
        old_values = getattr(instance, '_pre_save_values', {})
        for campo in WATCHED_FIELDS:
            if campo not in old_values:
                continue
            old_val = old_values[campo]
            new_val = getattr(instance, campo)
            if old_val == new_val:
                continue
            try:
                ejecutar_automatizaciones_por_evento(
                    lead_id=lead_pk,
                    campo=campo,
                    valor_anterior=str(old_val) if old_val is not None else '',
                    valor_nuevo=str(new_val) if new_val is not None else '',
                )
            except Exception as e:
                logger.error('Error procesando evento %s:%s→%s lead #%s: %s',
                             campo, old_val, new_val, lead_pk, e)

    try:
        ejecutar_automatizaciones_inmediatas(lead_id=lead_pk)
    except Exception as e:
        logger.error('Error procesando automatizaciones inmediatas lead #%s: %s', lead_pk, e)
