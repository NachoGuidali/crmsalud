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

        # Reglas de Automatización con ventana de tiempo (Inmediatamente se evalúa
        # síncronamente vía señal; estas necesitan escaneo periódico — incluyendo
        # delays en minutos/horas, por eso corre cada 10 minutos en vez de cada hora)
        schedule_10m, _ = IntervalSchedule.objects.get_or_create(
            every=10, period=IntervalSchedule.MINUTES
        )
        task, _ = PeriodicTask.objects.get_or_create(
            name='ejecutar_automatizaciones',
            defaults={
                'task': 'apps.automations.tasks.ejecutar_automatizaciones',
                'interval': schedule_10m,
                'enabled': True,
            },
        )
        if task.interval_id != schedule_10m.id:
            task.interval = schedule_10m
            task.save(update_fields=['interval'])

        # Reglas "campo de fecha = referencia ± offset" (ej: cumpleaños) — cron diario
        schedule_1d, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.DAYS
        )
        PeriodicTask.objects.get_or_create(
            name='ejecutar_automatizaciones_fecha_campo',
            defaults={
                'task': 'apps.automations.tasks.ejecutar_automatizaciones_fecha_campo',
                'interval': schedule_1d,
                'enabled': True,
            },
        )
    except Exception:
        pass
