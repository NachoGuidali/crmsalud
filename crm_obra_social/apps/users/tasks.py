from celery import shared_task


@shared_task
def marcar_agentes_inactivos():
    """Mark agents as off-duty if they haven't pinged in the last 10 minutes."""
    from django.utils import timezone
    from datetime import timedelta
    from .models import User

    cutoff = timezone.now() - timedelta(minutes=10)
    inactivos = User.objects.filter(
        disponible=True,
        ultimo_ping_at__isnull=False,
        ultimo_ping_at__lt=cutoff,
    )
    for user in inactivos:
        user.disponible = False
        user.save(update_fields=['disponible'])  # triggers post_save → redistribution
