import uuid
from django.conf import settings
from django.db import models


class ApiKey(models.Model):
    """API key for external integrations (web forms, landing pages, CRMs, etc.)."""

    nombre = models.CharField(max_length=200, verbose_name='Nombre / origen')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    activa = models.BooleanField(default=True, db_index=True)

    # Defaults applied when creating leads via this key
    origen_default = models.CharField(
        max_length=20, verbose_name='Origen por defecto',
        choices=[
            ('web', 'Web'), ('campana', 'Campaña'), ('referido', 'Referido'),
            ('llamada', 'Llamada entrante'), ('whatsapp', 'WhatsApp'),
        ],
        default='web',
    )
    agente_default = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='Agente asignado por defecto',
    )
    estado_inicial = models.CharField(
        max_length=20, default='nuevo', verbose_name='Estado inicial del lead',
    )

    # Stats
    ultimo_uso_at = models.DateTimeField(null=True, blank=True, verbose_name='Último uso')
    total_usos = models.PositiveIntegerField(default=0, verbose_name='Total de usos')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'
        ordering = ['-created_at']

    def __str__(self):
        estado = '✅' if self.activa else '🔴'
        return f'{estado} {self.nombre}'

    @property
    def key_display(self):
        """Show only last 8 chars for security in lists."""
        return f'...{str(self.key)[-8:]}'


class WebhookLog(models.Model):
    """Logs every inbound API call for debugging and auditing."""

    STATUS_OK = 'ok'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [(STATUS_OK, 'OK'), (STATUS_ERROR, 'Error')]

    api_key = models.ForeignKey(ApiKey, null=True, blank=True, on_delete=models.SET_NULL, related_name='logs')
    endpoint = models.CharField(max_length=200)
    method = models.CharField(max_length=10)
    ip = models.GenericIPAddressField(null=True, blank=True)
    request_body = models.TextField(blank=True)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OK)
    lead_creado = models.ForeignKey(
        'leads.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='webhook_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de webhook'
        verbose_name_plural = 'Logs de webhook'
        ordering = ['-created_at']
