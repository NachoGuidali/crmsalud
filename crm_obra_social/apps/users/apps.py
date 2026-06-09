from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    verbose_name = 'Usuarios'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out
        from django.db.models.signals import post_migrate

        def _on_login(sender, request, user, **kwargs):
            from django.utils import timezone
            user.disponible = True
            user.ultimo_ping_at = timezone.now()
            user.save(update_fields=['disponible', 'ultimo_ping_at'])

        def _on_logout(sender, request, user, **kwargs):
            if user:
                user.disponible = False
                user.ultimo_ping_at = None
                user.save(update_fields=['disponible', 'ultimo_ping_at'])

        user_logged_in.connect(_on_login, weak=False)
        user_logged_out.connect(_on_logout, weak=False)

        post_migrate.connect(_setup_periodic_task, sender=self)


def _setup_periodic_task(sender, **kwargs):
    try:
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        schedule_5m, _ = IntervalSchedule.objects.get_or_create(
            every=5, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.get_or_create(
            name='marcar_agentes_inactivos',
            defaults={
                'task': 'apps.users.tasks.marcar_agentes_inactivos',
                'interval': schedule_5m,
                'enabled': True,
            },
        )
    except Exception:
        pass
