from django.apps import AppConfig


class AutomationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.automations'
    verbose_name = 'Automatizaciones'

    def ready(self):
        import apps.automations.signals  # noqa: F401 — registers signal handlers
        from django.db.models.signals import post_migrate
        post_migrate.connect(_setup_periodic_tasks, sender=self)


def _setup_periodic_tasks(sender, **kwargs):
    try:
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        schedule_1h, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.HOURS
        )
        PeriodicTask.objects.get_or_create(
            name='ejecutar_automatizaciones',
            defaults={
                'task': 'apps.automations.tasks.ejecutar_automatizaciones',
                'interval': schedule_1h,
                'enabled': True,
            },
        )
    except Exception:
        pass
