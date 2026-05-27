from django.apps import AppConfig


class CampaignsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.campaigns'
    verbose_name = 'Campañas'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_setup_periodic_tasks, sender=self)


def _setup_periodic_tasks(sender, **kwargs):
    """Auto-create Celery Beat periodic task for scheduled campaigns."""
    try:
        from django_celery_beat.models import PeriodicTask, IntervalSchedule

        schedule_5m, _ = IntervalSchedule.objects.get_or_create(
            every=5, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.get_or_create(
            name='lanzar_campanas_programadas',
            defaults={
                'task': 'apps.campaigns.tasks.lanzar_campanas_programadas',
                'interval': schedule_5m,
                'enabled': True,
            },
        )
    except Exception:
        pass
