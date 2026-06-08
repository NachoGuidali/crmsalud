from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DeleteView
from django.urls import reverse_lazy

from apps.leads.models import Lead
from apps.whatsapp.models import PlantillaHSM
from .models import ReglaAutomatizacion, CondicionRegla, AutomatizacionLog


class SupervisorMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


class ReglaListView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'automations/regla_list.html'

    def get(self, request):
        reglas = ReglaAutomatizacion.objects.prefetch_related('condiciones').all()
        return render(request, self.template_name, {'reglas': reglas})


class ReglaCreateView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'automations/regla_form.html'

    def get(self, request):
        return render(request, self.template_name, _form_ctx())

    def post(self, request):
        err = _save_regla(request.POST, None)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, _form_ctx(request.POST))
        messages.success(request, 'Regla creada correctamente.')
        return redirect('automations:list')


class ReglaUpdateView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'automations/regla_form.html'

    def get(self, request, pk):
        regla = get_object_or_404(ReglaAutomatizacion, pk=pk)
        return render(request, self.template_name, _form_ctx(instance=regla))

    def post(self, request, pk):
        regla = get_object_or_404(ReglaAutomatizacion, pk=pk)
        err = _save_regla(request.POST, regla)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, _form_ctx(request.POST, regla))
        messages.success(request, 'Regla actualizada.')
        return redirect('automations:list')


class ReglaToggleView(LoginRequiredMixin, SupervisorMixin, View):
    """AJAX: toggle regla activa/inactiva."""
    def post(self, request, pk):
        regla = get_object_or_404(ReglaAutomatizacion, pk=pk)
        regla.activa = not regla.activa
        regla.save(update_fields=['activa'])
        return JsonResponse({'activa': regla.activa})


class ReglaDeleteView(LoginRequiredMixin, SupervisorMixin, DeleteView):
    model = ReglaAutomatizacion
    template_name = 'automations/regla_confirm_delete.html'
    success_url = reverse_lazy('automations:list')

    def form_valid(self, form):
        messages.success(self.request, 'Regla eliminada.')
        return super().form_valid(form)


class ReglaEjecutarView(LoginRequiredMixin, SupervisorMixin, View):
    """Manually trigger a single time-window Automatización rule immediately (for testing)."""
    def post(self, request, pk):
        regla = get_object_or_404(ReglaAutomatizacion, pk=pk)
        if regla.es_event_based:
            messages.warning(request, 'Las reglas de tipo "Disparador" se ejecutan automáticamente al ocurrir el evento; no se pueden ejecutar manualmente.')
            return redirect('automations:list')
        from django.utils import timezone
        try:
            now = timezone.now()
            if regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_INMEDIATO:
                messages.warning(request, 'Las reglas "Inmediatamente" se ejecutan automáticamente al guardar el lead; no se pueden ejecutar manualmente.')
                return redirect('automations:list')
            elif regla.trigger_tipo == ReglaAutomatizacion.TRIGGER_FECHA_CAMPO:
                from .tasks import _ejecutar_regla_fecha_campo
                count = _ejecutar_regla_fecha_campo(regla, now)
            else:
                from .tasks import _ejecutar_regla
                count = _ejecutar_regla(regla, now)
            messages.success(request, f'Regla ejecutada manualmente: {count} lead(s) afectado(s).')
        except Exception as e:
            messages.error(request, f'Error al ejecutar la regla: {e}')
        return redirect('automations:list')


class LogListView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'automations/log_list.html'

    def get(self, request):
        qs = AutomatizacionLog.objects.select_related('regla', 'lead').order_by('-ejecutado_at')
        paginator = Paginator(qs, 50)
        page = paginator.get_page(request.GET.get('page'))
        return render(request, self.template_name, {'logs': page})


# --- Helpers ---

FECHA_CAMPO_CHOICES = [
    ('fecha_nacimiento', 'Fecha de nacimiento'),
    ('created_at', 'Fecha de creación del lead'),
]


def _campo_choices():
    from apps.leads.models import CampoPersonalizado
    choices = [
        ('estado', 'Estado'),
        ('prioridad', 'Prioridad'),
        ('origen', 'Origen'),
        ('agente', 'Agente / Responsable'),
        ('plan_interes', 'Plan de interés'),
    ]
    choices += [
        (f'cp:{cp.slug}', cp.nombre)
        for cp in CampoPersonalizado.objects.filter(activo=True, alcance__in=['leads', 'ambos'])
    ]
    return choices


def _condiciones_desde_post(data):
    campos = data.getlist('condicion_campo[]')
    operadores = data.getlist('condicion_operador[]')
    valores = data.getlist('condicion_valor[]')
    joins = data.getlist('condicion_join[]')
    out = []
    for i, campo in enumerate(campos):
        out.append({
            'campo': campo,
            'operador': operadores[i] if i < len(operadores) else CondicionRegla.OP_EQ,
            'valor': valores[i] if i < len(valores) else '',
            'join': joins[i] if i < len(joins) else CondicionRegla.JOIN_AND,
        })
    return out


def _form_ctx(data=None, instance=None):
    from apps.users.models import User

    if data:
        condiciones = _condiciones_desde_post(data)
    elif instance and instance.pk:
        condiciones = [
            {'campo': c.campo, 'operador': c.operador, 'valor': c.valor, 'join': c.join_siguiente}
            for c in instance.condiciones.all()
        ]
    else:
        condiciones = []

    ctx = {
        'instance': instance,
        'data': data or {},
        'tipo_regla_choices': ReglaAutomatizacion.TIPO_REGLA_CHOICES,
        'trigger_choices_automatizacion': ReglaAutomatizacion.TRIGGER_CHOICES_AUTOMATIZACION,
        'trigger_choices_disparador': ReglaAutomatizacion.TRIGGER_CHOICES_DISPARADOR,
        'delay_unidad_choices': ReglaAutomatizacion.DELAY_UNIDAD_CHOICES,
        'offset_signo_choices': ReglaAutomatizacion.OFFSET_SIGNO_CHOICES,
        'fecha_campo_choices': FECHA_CAMPO_CHOICES,
        'accion_choices': ReglaAutomatizacion.ACCION_CHOICES,
        'estado_choices': Lead.ESTADO_CHOICES,
        'prioridad_choices': Lead.PRIORIDAD_CHOICES,
        'origen_choices': Lead.ORIGEN_CHOICES,
        'campo_choices': _campo_choices(),
        'condicion_operador_choices': CondicionRegla.OPERADOR_CHOICES,
        'condicion_join_choices': CondicionRegla.JOIN_CHOICES,
        'condiciones_json': condiciones,
        'plantillas': PlantillaHSM.objects.filter(activa=True),
        'agentes': User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
    }
    return ctx


def _save_regla(data, instance):
    """Validate and save a ReglaAutomatizacion + sus CondicionRegla. Returns error string or None."""
    from apps.users.models import User

    nombre = data.get('nombre', '').strip()
    if not nombre:
        return 'El nombre es requerido.'

    tipo_regla = data.get('tipo_regla', '')
    if tipo_regla not in dict(ReglaAutomatizacion.TIPO_REGLA_CHOICES):
        return 'Tipo de regla inválido.'

    trigger_tipo = data.get('trigger_tipo', '')
    triggers_validos = dict(
        ReglaAutomatizacion.TRIGGER_CHOICES_AUTOMATIZACION
        if tipo_regla == ReglaAutomatizacion.TIPO_AUTOMATIZACION
        else ReglaAutomatizacion.TRIGGER_CHOICES_DISPARADOR
    )
    if trigger_tipo not in triggers_validos:
        return 'Disparador inválido para el tipo de regla seleccionado.'

    accion_tipo = data.get('accion_tipo', '')
    if accion_tipo not in dict(ReglaAutomatizacion.ACCION_CHOICES):
        return 'Acción inválida.'

    # --- Condiciones (arrays paralelos condicion_campo[]/operador[]/valor[]/join[]) ---
    operadores_validos = dict(CondicionRegla.OPERADOR_CHOICES)
    joins_validos = dict(CondicionRegla.JOIN_CHOICES)
    condiciones_data = []
    for c in _condiciones_desde_post(data):
        campo = c['campo'].strip()
        if not campo:
            continue
        if c['operador'] not in operadores_validos:
            return f'Operador de condición inválido: {c["operador"]}'
        join = c['join'] if c['join'] in joins_validos else CondicionRegla.JOIN_AND
        condiciones_data.append({'campo': campo, 'operador': c['operador'], 'valor': c['valor'].strip(), 'join': join})

    if instance is None:
        instance = ReglaAutomatizacion()

    instance.nombre      = nombre
    instance.descripcion = data.get('descripcion', '').strip()
    instance.activa      = data.get('activa') == 'on'
    instance.orden       = int(data.get('orden', 0) or 0)
    instance.tipo_regla  = tipo_regla
    instance.trigger_tipo = trigger_tipo

    # Resetear todos los campos variantes del trigger; sólo se completan los que aplican
    instance.trigger_dias             = None
    instance.delay_cantidad           = None
    instance.delay_unidad             = ReglaAutomatizacion.DELAY_DIAS
    instance.fecha_campo_objetivo     = ''
    instance.fecha_campo_offset_dias  = None
    instance.fecha_campo_offset_signo = ReglaAutomatizacion.OFFSET_DESPUES
    instance.trigger_campo            = ''
    instance.trigger_valor_anterior   = ''
    instance.trigger_valor_nuevo      = ''

    if trigger_tipo in (ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_CAMBIO, ReglaAutomatizacion.TRIGGER_TIEMPO_SIN_WA):
        try:
            trigger_dias = int(data.get('trigger_dias', 0))
            if trigger_dias < 0:
                raise ValueError
        except (ValueError, TypeError):
            return 'Los días del disparador deben ser un número positivo.'
        instance.trigger_dias = trigger_dias

    elif trigger_tipo == ReglaAutomatizacion.TRIGGER_DELAY:
        try:
            delay_cantidad = int(data.get('delay_cantidad', 0))
            if delay_cantidad < 0:
                raise ValueError
        except (ValueError, TypeError):
            return 'La cantidad de "En X tiempo" debe ser un número positivo.'
        delay_unidad = data.get('delay_unidad', '')
        if delay_unidad not in dict(ReglaAutomatizacion.DELAY_UNIDAD_CHOICES):
            return 'Unidad de tiempo inválida.'
        instance.delay_cantidad = delay_cantidad
        instance.delay_unidad = delay_unidad

    elif trigger_tipo == ReglaAutomatizacion.TRIGGER_FECHA_CAMPO:
        fecha_campo_objetivo = data.get('fecha_campo_objetivo', '').strip()
        if not fecha_campo_objetivo:
            return 'Elegí el campo de fecha de referencia.'
        try:
            offset_dias = int(data.get('fecha_campo_offset_dias', 0) or 0)
            if offset_dias < 0:
                raise ValueError
        except (ValueError, TypeError):
            return 'El offset en días debe ser un número positivo.'
        offset_signo = data.get('fecha_campo_offset_signo', '')
        if offset_signo not in dict(ReglaAutomatizacion.OFFSET_SIGNO_CHOICES):
            return 'Signo de offset inválido.'
        instance.fecha_campo_objetivo = fecha_campo_objetivo
        instance.fecha_campo_offset_dias = offset_dias
        instance.fecha_campo_offset_signo = offset_signo

    elif trigger_tipo in (ReglaAutomatizacion.TRIGGER_CAMPO_CAMBIA, ReglaAutomatizacion.TRIGGER_CAMPO_IGUAL_A):
        trigger_campo = data.get('trigger_campo', '').strip()
        if not trigger_campo:
            return 'Elegí el campo a observar.'
        instance.trigger_campo = trigger_campo
        if trigger_tipo == ReglaAutomatizacion.TRIGGER_CAMPO_IGUAL_A:
            valor_nuevo = data.get('trigger_valor_nuevo', '').strip()
            if not valor_nuevo:
                return 'Elegí el valor nuevo que debe tomar el campo.'
            instance.trigger_valor_anterior = data.get('trigger_valor_anterior', '').strip()
            instance.trigger_valor_nuevo = valor_nuevo

    # inmediato / creado / responsable_cambia: no necesitan campos extra

    instance.accion_tipo = accion_tipo
    instance.accion_estado_destino      = data.get('accion_estado_destino', '')
    instance.accion_prioridad_destino   = data.get('accion_prioridad_destino', '')
    instance.accion_tarea_descripcion   = data.get('accion_tarea_descripcion', '').strip()
    instance.accion_tarea_dias_plazo    = int(data.get('accion_tarea_dias_plazo', 1) or 1)
    instance.accion_mensaje_texto       = data.get('accion_mensaje_texto', '').strip()
    instance.accion_webhook_url         = data.get('accion_webhook_url', '').strip()

    plantilla_id = data.get('accion_plantilla')
    instance.accion_plantilla = PlantillaHSM.objects.get(pk=plantilla_id) if plantilla_id else None

    agente_id = data.get('accion_agente')
    if agente_id:
        try:
            instance.accion_agente = User.objects.get(pk=agente_id)
        except User.DoesNotExist:
            instance.accion_agente = None
    else:
        instance.accion_agente = None

    instance.save()

    # Reemplazar condiciones — set simple, no hay edición concurrente de estas sub-filas
    instance.condiciones.all().delete()
    for orden, c in enumerate(condiciones_data):
        CondicionRegla.objects.create(
            regla=instance, orden=orden,
            campo=c['campo'], operador=c['operador'], valor=c['valor'], join_siguiente=c['join'],
        )

    return None
