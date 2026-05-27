from django.conf import settings
from django.db import models
from django.utils import timezone


class Tarea(models.Model):
    TIPO_LLAMADA = 'llamada'
    TIPO_WHATSAPP = 'whatsapp'
    TIPO_REUNION = 'reunion'
    TIPO_DOC = 'documentacion'
    TIPO_SEGUIMIENTO = 'seguimiento'
    TIPO_CHOICES = [
        (TIPO_LLAMADA, 'Llamada'),
        (TIPO_WHATSAPP, 'WhatsApp'),
        (TIPO_REUNION, 'Reunión'),
        (TIPO_DOC, 'Envío de documentación'),
        (TIPO_SEGUIMIENTO, 'Seguimiento'),
    ]

    STATUS_PENDIENTE = 'pendiente'
    STATUS_COMPLETADA = 'completada'
    STATUS_VENCIDA = 'vencida'
    STATUS_CHOICES = [
        (STATUS_PENDIENTE, 'Pendiente'),
        (STATUS_COMPLETADA, 'Completada'),
        (STATUS_VENCIDA, 'Vencida'),
    ]

    lead = models.ForeignKey(
        'leads.Lead', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tareas',
    )
    cliente = models.ForeignKey(
        'clientes.Cliente', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tareas',
    )
    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tareas',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_SEGUIMIENTO)
    descripcion = models.TextField(verbose_name='Descripción')
    fecha_programada = models.DateTimeField(verbose_name='Fecha y hora programada')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDIENTE, db_index=True)
    resultado = models.TextField(blank=True, verbose_name='Resultado / nota de completado')
    notificacion_enviada = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tarea'
        verbose_name_plural = 'Tareas'
        ordering = ['fecha_programada']

    def __str__(self):
        contacto = self.lead or self.cliente or 'Sin contacto'
        return f'{self.get_tipo_display()} — {contacto} @ {self.fecha_programada.strftime("%d/%m/%Y %H:%M")}'

    @property
    def contacto(self):
        return self.lead or self.cliente

    @property
    def contacto_nombre(self):
        if self.lead:
            return self.lead.nombre_completo
        if self.cliente:
            return self.cliente.nombre_completo
        return '—'

    @property
    def is_vencida(self):
        return self.status == self.STATUS_PENDIENTE and self.fecha_programada < timezone.now()

    def get_tipo_icon(self):
        return {
            self.TIPO_LLAMADA: 'phone',
            self.TIPO_WHATSAPP: 'whatsapp',
            self.TIPO_REUNION: 'people',
            self.TIPO_DOC: 'file-earmark',
            self.TIPO_SEGUIMIENTO: 'arrow-repeat',
        }.get(self.tipo, 'check2')
