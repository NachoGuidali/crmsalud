from django.apps import AppConfig


class DealsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.deals'
    verbose_name = 'Negociaciones'

    def ready(self):
        import apps.deals.signals  # noqa: F401
