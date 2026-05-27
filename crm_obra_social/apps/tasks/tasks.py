from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task
def marcar_tareas_vencidas():
    """Mark overdue pending tasks. Run via Celery Beat every 15 minutes."""
    from .models import Tarea
    now = timezone.now()
    updated = Tarea.objects.filter(status=Tarea.STATUS_PENDIENTE, fecha_programada__lt=now).update(status=Tarea.STATUS_VENCIDA)
    return f'{updated} tareas marcadas como vencidas.'


@shared_task
def notificar_tareas_proximas():
    """Log upcoming tasks (within 30 min) that haven't been notified yet."""
    import logging
    from .models import Tarea
    logger = logging.getLogger('apps.tasks')
    now = timezone.now()
    ventana = now + timedelta(minutes=30)
    tareas = Tarea.objects.filter(
        status=Tarea.STATUS_PENDIENTE,
        fecha_programada__range=(now, ventana),
        notificacion_enviada=False,
    ).select_related('lead', 'agente')
    for tarea in tareas:
        logger.info('Upcoming task reminder: %s for lead %s (agent: %s)', tarea, tarea.lead, tarea.agente)
        tarea.notificacion_enviada = True
        tarea.save(update_fields=['notificacion_enviada'])
    return f'{tareas.count()} notificaciones enviadas.'
