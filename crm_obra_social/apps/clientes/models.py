from django.conf import settings
from django.db import models

from utils.phone import normalize_ar_phone


class Cliente(models.Model):
    nombre_completo  = models.CharField(max_length=200, verbose_name='Nombre completo')
    dni              = models.CharField(max_length=20, blank=True, verbose_name='DNI')
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name='Fecha de nacimiento')
    telefono         = models.CharField(max_length=30, blank=True, verbose_name='Teléfono')
    email            = models.EmailField(blank=True, verbose_name='Email')
    localidad        = models.CharField(max_length=100, blank=True, verbose_name='Localidad')
    provincia        = models.CharField(max_length=100, blank=True, verbose_name='Provincia')

    plan             = models.ForeignKey('leads.Plan', null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Plan')
    numero_afiliado  = models.CharField(max_length=50, blank=True, verbose_name='N° de afiliado')
    grupo_familiar   = models.PositiveSmallIntegerField(default=1, verbose_name='Grupo familiar')

    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='clientes_asignados',
        verbose_name='Agente',
    )
    notas      = models.TextField(blank=True, verbose_name='Notas')
    datos_extra = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def save(self, *args, **kwargs):
        if self.telefono:
            self.telefono = normalize_ar_phone(self.telefono)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre_completo
