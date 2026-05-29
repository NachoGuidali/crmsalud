from django.conf import settings
from django.db import models


class Pipeline(models.Model):
    nombre      = models.CharField(max_length=100, verbose_name='Nombre')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    activo      = models.BooleanField(default=True, verbose_name='Activo')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Pipeline'
        verbose_name_plural = 'Pipelines'

    def __str__(self):
        return self.nombre

    @property
    def total_deals(self):
        return self.deals.count()

    @property
    def valor_total(self):
        return self.deals.aggregate(t=models.Sum('valor'))['t'] or 0


class PipelineStage(models.Model):
    COLOR_CHOICES = [
        ('primary',   'Azul'),
        ('success',   'Verde'),
        ('warning',   'Amarillo'),
        ('danger',    'Rojo'),
        ('info',      'Celeste'),
        ('secondary', 'Gris'),
        ('dark',      'Oscuro'),
    ]

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stages')
    nombre   = models.CharField(max_length=100, verbose_name='Nombre de la etapa')
    orden    = models.PositiveSmallIntegerField(default=0, verbose_name='Orden')
    color    = models.CharField(max_length=20, choices=COLOR_CHOICES, default='primary', verbose_name='Color')

    class Meta:
        ordering = ['pipeline', 'orden', 'nombre']
        unique_together = [('pipeline', 'nombre')]
        verbose_name = 'Etapa'
        verbose_name_plural = 'Etapas'

    def __str__(self):
        return f'{self.pipeline.nombre} / {self.nombre}'


class Deal(models.Model):
    titulo                = models.CharField(max_length=200, verbose_name='Título')
    pipeline              = models.ForeignKey(Pipeline, on_delete=models.PROTECT, related_name='deals', verbose_name='Pipeline')
    stage                 = models.ForeignKey(PipelineStage, on_delete=models.PROTECT, related_name='deals', verbose_name='Etapa')
    valor                 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor estimado ($)')
    lead                  = models.ForeignKey('leads.Lead', null=True, blank=True, on_delete=models.SET_NULL, related_name='deals', verbose_name='Lead asociado')
    nombre_contacto       = models.CharField(max_length=200, blank=True, verbose_name='Nombre del contacto')
    agente                = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='deals', verbose_name='Agente responsable')
    descripcion           = models.TextField(blank=True, verbose_name='Descripción / notas')
    fecha_cierre_estimada = models.DateField(null=True, blank=True, verbose_name='Fecha de cierre estimada')
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Negociación'
        verbose_name_plural = 'Negociaciones'

    def __str__(self):
        return self.titulo

    @property
    def contacto_display(self):
        if self.lead_id:
            return self.lead.nombre_completo
        return self.nombre_contacto or '—'

    @property
    def dias_en_etapa(self):
        last = self.history.first()
        if last:
            from django.utils import timezone
            return (timezone.now() - last.created_at).days
        from django.utils import timezone
        return (timezone.now() - self.created_at).days


class DealHistory(models.Model):
    deal           = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='history')
    stage_anterior = models.ForeignKey(PipelineStage, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    stage_nuevo    = models.ForeignKey(PipelineStage, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    cambiado_por   = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    nota           = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Historial de etapa'
        verbose_name_plural = 'Historial de etapas'

    def __str__(self):
        ant = self.stage_anterior.nombre if self.stage_anterior else '—'
        nvo = self.stage_nuevo.nombre if self.stage_nuevo else '—'
        return f'{self.deal.titulo}: {ant} → {nvo}'
