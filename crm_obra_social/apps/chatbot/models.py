from django.db import models
from django.conf import settings


class ChatBot(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='chatbots',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Chatbot'
        verbose_name_plural = 'Chatbots'

    def __str__(self):
        return self.nombre


class ChatBotFlow(models.Model):
    bot = models.OneToOneField(ChatBot, on_delete=models.CASCADE, related_name='flow')
    drawflow_data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Flow: {self.bot.nombre}'
