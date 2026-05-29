import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

logger = logging.getLogger('apps.deals')


@receiver(pre_save, sender='deals.Deal')
def deal_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.only('stage_id').get(pk=instance.pk)
            instance._old_stage_id = old.stage_id
        except sender.DoesNotExist:
            instance._old_stage_id = None
    else:
        instance._old_stage_id = None


@receiver(post_save, sender='deals.Deal')
def deal_post_save(sender, instance, created, **kwargs):
    old_stage_id = getattr(instance, '_old_stage_id', None)
    if created or old_stage_id is None or old_stage_id == instance.stage_id:
        return

    from apps.deals.models import DealHistory, PipelineStage

    try:
        old_stage = PipelineStage.objects.get(pk=old_stage_id)
    except PipelineStage.DoesNotExist:
        old_stage = None

    DealHistory.objects.create(
        deal=instance,
        stage_anterior=old_stage,
        stage_nuevo=instance.stage,
        cambiado_por=getattr(instance, '_cambiado_por', None),
    )

    # Fire automations for the linked lead (if any)
    if instance.lead_id:
        try:
            from apps.automations.tasks import ejecutar_automatizaciones_por_evento
            ejecutar_automatizaciones_por_evento(
                lead_id=instance.lead_id,
                campo='deal_stage',
                valor_anterior=old_stage.nombre if old_stage else str(old_stage_id),
                valor_nuevo=instance.stage.nombre,
            )
        except Exception as e:
            logger.error('Error disparando automatización por deal stage: %s', e)
