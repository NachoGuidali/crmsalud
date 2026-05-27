from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class CampoPersonalizado(models.Model):
    TIPO_TEXTO    = 'texto'
    TIPO_NUMERO   = 'numero'
    TIPO_FECHA    = 'fecha'
    TIPO_BOOLEANO = 'booleano'
    TIPO_LISTA    = 'lista'
    TIPO_CHOICES = [
        ('texto',    'Texto libre'),
        ('numero',   'Número'),
        ('fecha',    'Fecha'),
        ('booleano', 'Sí / No'),
        ('lista',    'Lista de opciones'),
    ]

    ALCANCE_LEADS    = 'leads'
    ALCANCE_CLIENTES = 'clientes'
    ALCANCE_AMBOS    = 'ambos'
    ALCANCE_CHOICES = [
        ('leads',    'Solo Leads'),
        ('clientes', 'Solo Clientes'),
        ('ambos',    'Leads y Clientes'),
    ]

    nombre   = models.CharField(max_length=100, unique=True, verbose_name='Nombre')
    slug     = models.SlugField(max_length=100, unique=True, verbose_name='Clave interna', editable=False)
    tipo     = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_TEXTO, verbose_name='Tipo')
    alcance  = models.CharField(max_length=20, choices=ALCANCE_CHOICES, default=ALCANCE_AMBOS, verbose_name='Aplica a')
    opciones = models.JSONField(default=list, blank=True, verbose_name='Opciones (para Lista)')
    requerido = models.BooleanField(default=False, verbose_name='Requerido')
    orden    = models.PositiveIntegerField(default=0, verbose_name='Orden')
    activo   = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Campo personalizado'
        verbose_name_plural = 'Campos personalizados'

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre)
            slug, n = base, 1
            while CampoPersonalizado.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Plan(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


dni_validator = RegexValidator(
    regex=r'^\d{7,8}$',
    message='El DNI debe tener entre 7 y 8 dígitos numéricos.',
)

phone_validator = RegexValidator(
    regex=r'^\+54\d{10,12}$',
    message='El teléfono debe comenzar con +54 seguido de 10-12 dígitos.',
)


class Lead(models.Model):
    # Pipeline states
    ESTADO_NUEVO = 'nuevo'
    ESTADO_CONTACTADO = 'contactado'
    ESTADO_INTERESADO = 'interesado'
    ESTADO_DOC_PENDIENTE = 'doc_pendiente'
    ESTADO_EN_REVISION = 'en_revision'
    ESTADO_AFILIADO = 'afiliado'
    ESTADO_PERDIDO = 'perdido'

    ESTADO_CHOICES = [
        (ESTADO_NUEVO, 'Nuevo'),
        (ESTADO_CONTACTADO, 'Contactado'),
        (ESTADO_INTERESADO, 'Interesado'),
        (ESTADO_DOC_PENDIENTE, 'Documentación pendiente'),
        (ESTADO_EN_REVISION, 'En revisión'),
        (ESTADO_AFILIADO, 'Afiliado'),
        (ESTADO_PERDIDO, 'Perdido / No interesado'),
    ]

    PRIORIDAD_ALTA = 'alta'
    PRIORIDAD_MEDIA = 'media'
    PRIORIDAD_BAJA = 'baja'
    PRIORIDAD_CHOICES = [
        (PRIORIDAD_ALTA, 'Alta'),
        (PRIORIDAD_MEDIA, 'Media'),
        (PRIORIDAD_BAJA, 'Baja'),
    ]

    ORIGEN_WEB = 'web'
    ORIGEN_CAMPANA = 'campana'
    ORIGEN_REFERIDO = 'referido'
    ORIGEN_LLAMADA = 'llamada'
    ORIGEN_WHATSAPP = 'whatsapp'
    ORIGEN_CHOICES = [
        (ORIGEN_WEB, 'Web'),
        (ORIGEN_CAMPANA, 'Campaña'),
        (ORIGEN_REFERIDO, 'Referido'),
        (ORIGEN_LLAMADA, 'Llamada entrante'),
        (ORIGEN_WHATSAPP, 'WhatsApp'),
    ]

    # Personal data
    nombre_completo = models.CharField(max_length=200, verbose_name='Nombre completo')
    dni = models.CharField(max_length=8, validators=[dni_validator], verbose_name='DNI', db_index=True)
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name='Fecha de nacimiento')
    telefono = models.CharField(max_length=20, validators=[phone_validator], verbose_name='Teléfono (WhatsApp)', db_index=True)
    email = models.EmailField(blank=True, verbose_name='Email')
    localidad = models.CharField(max_length=100, blank=True, verbose_name='Localidad')
    provincia = models.CharField(max_length=100, blank=True, verbose_name='Provincia')

    # Commercial data
    plan_interes = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Plan de interés')
    grupo_familiar = models.PositiveSmallIntegerField(default=1, verbose_name='Cantidad grupo familiar')
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default=ORIGEN_WEB, verbose_name='Origen')

    # CRM
    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='leads_asignados',
        verbose_name='Agente asignado',
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_NUEVO, verbose_name='Estado', db_index=True)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default=PRIORIDAD_MEDIA, verbose_name='Prioridad')
    notas = models.TextField(blank=True, verbose_name='Notas internas')

    # Extra data from imports — stores any custom columns (empresa, cargo, etc.)
    datos_extra = models.JSONField(
        default=dict, blank=True,
        verbose_name='Datos extra',
        help_text='Columnas adicionales importadas desde CSV/Excel.',
    )

    motivo_perdida = models.TextField(
        blank=True,
        verbose_name='Motivo de pérdida',
        help_text='Completar cuando el lead se marca como "Perdido / No interesado".',
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.nombre_completo} ({self.dni})'

    def get_estado_badge_class(self):
        mapping = {
            self.ESTADO_NUEVO: 'secondary',
            self.ESTADO_CONTACTADO: 'info',
            self.ESTADO_INTERESADO: 'primary',
            self.ESTADO_DOC_PENDIENTE: 'warning',
            self.ESTADO_EN_REVISION: 'warning',
            self.ESTADO_AFILIADO: 'success',
            self.ESTADO_PERDIDO: 'danger',
        }
        return mapping.get(self.estado, 'secondary')

    def get_prioridad_badge_class(self):
        return {'alta': 'danger', 'media': 'warning', 'baja': 'success'}.get(self.prioridad, 'secondary')


class Documento(models.Model):
    TIPO_RECIBO = 'recibo_sueldo'
    TIPO_DNI = 'dni'
    TIPO_CONTRATO = 'contrato'
    TIPO_OTRO = 'otro'
    TIPO_CHOICES = [
        (TIPO_RECIBO, 'Recibo de sueldo'),
        (TIPO_DNI, 'DNI'),
        (TIPO_CONTRATO, 'Contrato / formulario'),
        (TIPO_OTRO, 'Otro'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='documentos')
    nombre = models.CharField(max_length=200, verbose_name='Descripción')
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_OTRO, verbose_name='Tipo')
    archivo = models.FileField(upload_to='documentos/%Y/%m/', verbose_name='Archivo')
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='documentos_subidos',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'

    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'

    @property
    def extension(self):
        name = self.archivo.name or ''
        return name.rsplit('.', 1)[-1].lower() if '.' in name else ''

    @property
    def icono(self):
        ext = self.extension
        if ext == 'pdf':
            return 'file-earmark-pdf text-danger'
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            return 'file-earmark-image text-primary'
        if ext in ('xlsx', 'xls', 'csv'):
            return 'file-earmark-spreadsheet text-success'
        if ext in ('docx', 'doc'):
            return 'file-earmark-word text-info'
        return 'file-earmark text-secondary'


class HistorialEstado(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='historial_estados')
    estado_anterior = models.CharField(max_length=20, choices=Lead.ESTADO_CHOICES, blank=True)
    estado_nuevo = models.CharField(max_length=20, choices=Lead.ESTADO_CHOICES)
    cambiado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    nota = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historial de estado'
        verbose_name_plural = 'Historial de estados'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.lead} — {self.estado_anterior} → {self.estado_nuevo}'
