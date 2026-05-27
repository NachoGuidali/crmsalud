from django.conf import settings
from django.db import models


class Cotizacion(models.Model):
    STATUS_BORRADOR = 'borrador'
    STATUS_ENVIADA = 'enviada'
    STATUS_ACEPTADA = 'aceptada'
    STATUS_RECHAZADA = 'rechazada'
    STATUS_CHOICES = [
        (STATUS_BORRADOR, 'Borrador'),
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_ACEPTADA, 'Aceptada'),
        (STATUS_RECHAZADA, 'Rechazada'),
    ]

    lead = models.ForeignKey('leads.Lead', on_delete=models.CASCADE, related_name='cotizaciones')
    plan = models.ForeignKey('leads.Plan', null=True, blank=True, on_delete=models.SET_NULL)
    cantidad_integrantes = models.PositiveSmallIntegerField(default=1)
    monto_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_BORRADOR)
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    pdf_file = models.FileField(upload_to='cotizaciones/pdf/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f'Cotización #{self.pk} — {self.lead}'


class IntegranteFamiliar(models.Model):
    PARENTESCO_TITULAR = 'titular'
    PARENTESCO_CONYUGE = 'conyuge'
    PARENTESCO_HIJO = 'hijo'
    PARENTESCO_OTRO = 'otro'
    PARENTESCO_CHOICES = [
        (PARENTESCO_TITULAR, 'Titular'),
        (PARENTESCO_CONYUGE, 'Cónyuge'),
        (PARENTESCO_HIJO, 'Hijo/a'),
        (PARENTESCO_OTRO, 'Otro'),
    ]

    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='integrantes')
    nombre = models.CharField(max_length=200)
    dni = models.CharField(max_length=8)
    fecha_nacimiento = models.DateField()
    parentesco = models.CharField(max_length=20, choices=PARENTESCO_CHOICES, default=PARENTESCO_TITULAR)

    class Meta:
        verbose_name = 'Integrante familiar'
        verbose_name_plural = 'Integrantes familiares'

    def __str__(self):
        return f'{self.nombre} ({self.get_parentesco_display()})'

    @property
    def edad(self):
        from django.utils import timezone
        hoy = timezone.localdate()
        born = self.fecha_nacimiento
        return hoy.year - born.year - ((hoy.month, hoy.day) < (born.month, born.day))
