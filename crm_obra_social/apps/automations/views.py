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
from .models import ReglaAutomatizacion, AutomatizacionLog


class SupervisorMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


class ReglaListView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'automations/regla_list.html'

    def get(self, request):
        reglas = ReglaAutomatizacion.objects.all()
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
    """Manually trigger a single time-based rule immediately (for testing)."""
    def post(self, request, pk):
        regla = get_object_or_404(ReglaAutomatizacion, pk=pk)
        if regla.es_event_based:
            messages.warning(request, 'Las reglas por evento se disparan automáticamente al cambiar el campo; no se pueden ejecutar manualmente.')
            return redirect('automations:list')
        from .tasks import _ejecutar_regla
        from django.utils import timezone
        try:
            count = _ejecutar_regla(regla, timezone.now())
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

def _form_ctx(data=None, instance=None):
    from apps.leads.models import Lead
    from apps.users.models import User
    ctx = {
        'instance': instance,
        'data': data or {},
        'trigger_choices': ReglaAutomatizacion.TRIGGER_CHOICES,
        'accion_choices': ReglaAutomatizacion.ACCION_CHOICES,
        'estado_choices': Lead.ESTADO_CHOICES,
        'prioridad_choices': Lead.PRIORIDAD_CHOICES,
        'origen_choices': Lead.ORIGEN_CHOICES,
        'plantillas': PlantillaHSM.objects.filter(activa=True),
        'agentes': User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'trigger_event': ReglaAutomatizacion.TRIGGER_ESTADO_CAMBIO,
    }
    return ctx


def _save_regla(data, instance):
    """Validate and save a ReglaAutomatizacion. Returns error string or None."""
    from apps.users.models import User

    nombre = data.get('nombre', '').strip()
    if not nombre:
        return 'El nombre es requerido.'

    trigger_tipo = data.get('trigger_tipo', '')
    if trigger_tipo not in dict(ReglaAutomatizacion.TRIGGER_CHOICES):
        return 'Disparador inválido.'

    is_event = (trigger_tipo == ReglaAutomatizacion.TRIGGER_ESTADO_CAMBIO)

    if not is_event:
        try:
            trigger_dias = int(data.get('trigger_dias', 0))
            if trigger_dias < 0:
                raise ValueError
        except (ValueError, TypeError):
            return 'Los días del disparador deben ser un número positivo.'
    else:
        trigger_dias = None

    accion_tipo = data.get('accion_tipo', '')
    if accion_tipo not in dict(ReglaAutomatizacion.ACCION_CHOICES):
        return 'Acción inválida.'

    if instance is None:
        instance = ReglaAutomatizacion()

    instance.nombre              = nombre
    instance.descripcion         = data.get('descripcion', '').strip()
    instance.activa              = data.get('activa') == 'on'
    instance.orden               = int(data.get('orden', 0) or 0)
    instance.trigger_tipo        = trigger_tipo
    instance.trigger_dias        = trigger_dias
    instance.trigger_campo       = data.get('trigger_campo', 'estado').strip() or 'estado'
    instance.trigger_valor_anterior = data.get('trigger_valor_anterior', '').strip()
    instance.trigger_valor_nuevo    = data.get('trigger_valor_nuevo', '').strip()
    instance.condicion_estado    = data.get('condicion_estado', '')
    instance.condicion_prioridad = data.get('condicion_prioridad', '')
    instance.condicion_origen    = data.get('condicion_origen', '')
    instance.accion_tipo         = accion_tipo
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
    return None
