from django.apps import AppConfig


class WhatsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.whatsapp'
    verbose_name = 'WhatsApp'

    def ready(self):
        from django.db.models.signals import post_save
        from django.conf import settings

        def _on_user_save(sender, instance, created, **kwargs):
            """Redistribute conversations when an agent becomes unavailable."""
            if created:
                return
            if not instance.is_active or not instance.disponible:
                try:
                    from apps.whatsapp.tasks import _redistribute_conversations
                    _redistribute_conversations(instance)
                except Exception as e:
                    import logging
                    logging.getLogger('apps.whatsapp').warning(
                        'Error redistributing convs for %s: %s', instance.username, e
                    )

        post_save.connect(_on_user_save, sender=settings.AUTH_USER_MODEL, weak=False)
