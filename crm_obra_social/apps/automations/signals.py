import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

logger = logging.getLogger('apps.automations')

WATCHED_FIELDS = ('estado', 'prioridad')


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
    """Fire event-based automations synchronously when a watched field changes."""
    if created or getattr(instance, '_skip_automation', False):
        return

    old_values = getattr(instance, '_pre_save_values', {})
    if not old_values:
        return

    from apps.automations.tasks import ejecutar_automatizaciones_por_evento

    lead_pk = instance.pk  # capture before any action deletes the lead
    for campo in WATCHED_FIELDS:
        old_val = old_values.get(campo)
        new_val = getattr(instance, campo)
        if old_val is not None and old_val != new_val:
            try:
                ejecutar_automatizaciones_por_evento(
                    lead_id=lead_pk,
                    campo=campo,
                    valor_anterior=old_val,
                    valor_nuevo=new_val,
                )
            except Exception as e:
                logger.error('Error procesando evento %s:%s→%s lead #%s: %s',
                             campo, old_val, new_val, lead_pk, e)
