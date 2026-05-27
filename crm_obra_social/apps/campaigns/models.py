from django.conf import settings
from django.db import models


class Campana(models.Model):
    STATUS_BORRADOR = 'borrador'
    STATUS_PROGRAMADA = 'programada'
    STATUS_EN_EJECUCION = 'en_ejecucion'
    STATUS_COMPLETADA = 'completada'
    STATUS_CHOICES = [
        (STATUS_BORRADOR, 'Borrador'),
        (STATUS_PROGRAMADA, 'Programada'),
        (STATUS_EN_EJECUCION, 'En ejecución'),
        (STATUS_COMPLETADA, 'Completada'),
    ]

    MODO_SEGMENTO = 'segmento'
    MODO_MANUAL = 'manual'
    MODO_CHOICES = [
        (MODO_SEGMENTO, 'Por segmento (filtros automáticos)'),
        (MODO_MANUAL, 'Selección manual de contactos'),
    ]

    TIPO_LEADS = 'leads'
    TIPO_CLIENTES = 'clientes'
    TIPO_TODOS = 'todos'
    TIPO_CHOICES = [
        (TIPO_LEADS, 'Solo Leads'),
        (TIPO_CLIENTES, 'Solo Clientes'),
        (TIPO_TODOS, 'Leads y Clientes'),
    ]

    nombre = models.CharField(max_length=200)
    plantilla = models.ForeignKey('whatsapp.PlantillaHSM', on_delete=models.PROTECT)
    modo_seleccion = models.CharField(max_length=10, choices=MODO_CHOICES, default=MODO_SEGMENTO)
    tipo_destinatario = models.CharField(
        max_length=10, choices=TIPO_CHOICES, default=TIPO_LEADS,
        verbose_name='Tipo de destinatarios',
    )
    filtros_segmento = models.JSONField(default=dict, blank=True)
    # Manual selection
    contactos_ids = models.JSONField(default=list, blank=True, verbose_name='Leads seleccionados')
    contactos_clientes_ids = models.JSONField(default=list, blank=True, verbose_name='Clientes seleccionados')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_BORRADOR)
    fecha_programada = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    variables_mapping = models.JSONField(default=list, blank=True)
    # Stats
    total_destinatarios = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    entregados = models.PositiveIntegerField(default=0)
    leidos = models.PositiveIntegerField(default=0)
    errores = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Campaña'
        verbose_name_plural = 'Campañas'
        ordering = ['-created_at']

    def __str__(self):
        return self.nombre

    def get_recipients(self):
        """Returns list of Lead + Cliente objects for this campaign."""
        from datetime import timedelta
        from apps.leads.models import Lead
        from apps.clientes.models import Cliente
        from django.utils import timezone

        if self.modo_seleccion == self.MODO_MANUAL:
            result = []
            if self.contactos_ids:
                result += list(Lead.objects.filter(
                    pk__in=self.contactos_ids, telefono__startswith='+'
                ).select_related('plan_interes'))
            if self.contactos_clientes_ids:
                result += list(Cliente.objects.filter(
                    pk__in=self.contactos_clientes_ids, telefono__startswith='+'
                ).select_related('plan'))
            return result

        f = self.filtros_segmento
        leads_list = []
        clientes_list = []

        def _apply_common_filters(qs, is_lead):
            if f.get('plan_id'):
                qs = qs.filter(plan_interes_id=f['plan_id']) if is_lead else qs.filter(plan_id=f['plan_id'])
            if f.get('provincia'):
                qs = qs.filter(provincia__icontains=f['provincia'])
            if f.get('dias_sin_contacto'):
                try:
                    cutoff = timezone.now() - timedelta(days=int(f['dias_sin_contacto']))
                    qs = qs.filter(updated_at__lt=cutoff)
                except (ValueError, TypeError):
                    pass
            return qs

        if self.tipo_destinatario in (self.TIPO_LEADS, self.TIPO_TODOS):
            qs = Lead.objects.filter(telefono__startswith='+').select_related('plan_interes')
            if f.get('estado'):
                qs = qs.filter(estado=f['estado'])
            qs = _apply_common_filters(qs, is_lead=True)
            leads_list = list(qs)

        if self.tipo_destinatario in (self.TIPO_CLIENTES, self.TIPO_TODOS):
            qs = Cliente.objects.filter(telefono__startswith='+').select_related('plan')
            qs = _apply_common_filters(qs, is_lead=False)
            clientes_list = list(qs)

        return leads_list + clientes_list

    def get_recipients_count(self):
        """Returns {'leads': N, 'clientes': M, 'total': N+M} using COUNT queries."""
        from datetime import timedelta
        from apps.leads.models import Lead
        from apps.clientes.models import Cliente
        from django.utils import timezone

        if self.modo_seleccion == self.MODO_MANUAL:
            lc = Lead.objects.filter(pk__in=self.contactos_ids or [], telefono__startswith='+').count()
            cc = Cliente.objects.filter(pk__in=self.contactos_clientes_ids or [], telefono__startswith='+').count()
            return {'leads': lc, 'clientes': cc, 'total': lc + cc}

        f = self.filtros_segmento
        lc = cc = 0

        def _apply_common_filters(qs, is_lead):
            if f.get('plan_id'):
                qs = qs.filter(plan_interes_id=f['plan_id']) if is_lead else qs.filter(plan_id=f['plan_id'])
            if f.get('provincia'):
                qs = qs.filter(provincia__icontains=f['provincia'])
            if f.get('dias_sin_contacto'):
                try:
                    cutoff = timezone.now() - timedelta(days=int(f['dias_sin_contacto']))
                    qs = qs.filter(updated_at__lt=cutoff)
                except (ValueError, TypeError):
                    pass
            return qs

        if self.tipo_destinatario in (self.TIPO_LEADS, self.TIPO_TODOS):
            qs = Lead.objects.filter(telefono__startswith='+')
            if f.get('estado'):
                qs = qs.filter(estado=f['estado'])
            lc = _apply_common_filters(qs, True).count()

        if self.tipo_destinatario in (self.TIPO_CLIENTES, self.TIPO_TODOS):
            qs = Cliente.objects.filter(telefono__startswith='+')
            cc = _apply_common_filters(qs, False).count()

        return {'leads': lc, 'clientes': cc, 'total': lc + cc}

    # Keep backward compat for old code paths
    def get_segment_queryset(self):
        from apps.leads.models import Lead
        if self.modo_seleccion == self.MODO_MANUAL and self.contactos_ids:
            return Lead.objects.filter(pk__in=self.contactos_ids, telefono__startswith='+')
        qs = Lead.objects.filter(telefono__startswith='+')
        f = self.filtros_segmento
        if f.get('estado'):
            qs = qs.filter(estado=f['estado'])
        if f.get('plan_id'):
            qs = qs.filter(plan_interes_id=f['plan_id'])
        if f.get('provincia'):
            qs = qs.filter(provincia__icontains=f['provincia'])
        return qs


class CampanaLog(models.Model):
    STATUS_ENVIADO = 'enviado'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_ENVIADO, 'Enviado'),
        (STATUS_ERROR, 'Error'),
    ]

    campana = models.ForeignKey(Campana, on_delete=models.CASCADE, related_name='logs')
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    telefono = models.CharField(max_length=20)
    nombre_contacto = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    whatsapp_message_id = models.CharField(max_length=100, blank=True)
    error_detalle = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de campaña'
        verbose_name_plural = 'Logs de campaña'
