import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView, DetailView, DeleteView
from django.urls import reverse_lazy

from .forms import CampanaForm
from .models import Campana
from .tasks import ejecutar_campana


class SupervisorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


class ContactoBuscarView(LoginRequiredMixin, View):
    """AJAX: search leads and/or clientes for campaign manual selection."""

    def get(self, request):
        from apps.leads.models import Lead
        from apps.clientes.models import Cliente
        from django.db.models import Q

        q = request.GET.get('q', '').strip()
        tipo = request.GET.get('tipo', 'todos')   # leads | clientes | todos
        page = int(request.GET.get('page', 1))

        results = []

        if tipo in ('leads', 'todos'):
            qs = Lead.objects.filter(telefono__startswith='+')
            if q:
                qs = qs.filter(
                    Q(nombre_completo__icontains=q) | Q(telefono__icontains=q) |
                    Q(email__icontains=q) | Q(dni__icontains=q)
                )
            for l in qs.order_by('nombre_completo')[:80]:
                results.append({
                    'id': l.pk,
                    'tipo': 'lead',
                    'nombre': l.nombre_completo,
                    'telefono': l.telefono,
                    'subtitulo': l.get_estado_display(),
                })

        if tipo in ('clientes', 'todos'):
            qs = Cliente.objects.filter(telefono__startswith='+')
            if q:
                qs = qs.filter(
                    Q(nombre_completo__icontains=q) | Q(telefono__icontains=q) |
                    Q(email__icontains=q) | Q(dni__icontains=q)
                )
            for c in qs.order_by('nombre_completo')[:80]:
                results.append({
                    'id': c.pk,
                    'tipo': 'cliente',
                    'nombre': c.nombre_completo,
                    'telefono': c.telefono,
                    'subtitulo': f'Cliente · {c.plan or "Sin plan"}',
                })

        results.sort(key=lambda x: x['nombre'].lower())

        paginator = Paginator(results, 25)
        pg = paginator.get_page(page)
        return JsonResponse({
            'results': list(pg),
            'has_next': pg.has_next(),
            'total': paginator.count,
        })


class CampanaPreviewCountView(LoginRequiredMixin, View):
    """AJAX: return recipient counts for current filter state (no save)."""

    def get(self, request):
        from apps.leads.models import Lead
        from apps.clientes.models import Cliente
        from datetime import timedelta
        from django.utils import timezone

        tipo = request.GET.get('tipo', 'leads')
        modo = request.GET.get('modo', 'segmento')

        if modo == 'manual':
            try:
                leads_ids = json.loads(request.GET.get('leads_ids', '[]'))
                clientes_ids = json.loads(request.GET.get('clientes_ids', '[]'))
            except (json.JSONDecodeError, TypeError):
                leads_ids, clientes_ids = [], []
            lc = Lead.objects.filter(pk__in=leads_ids, telefono__startswith='+').count()
            cc = Cliente.objects.filter(pk__in=clientes_ids, telefono__startswith='+').count()
            return JsonResponse({'total': lc + cc, 'leads': lc, 'clientes': cc})

        # Segment mode
        estado = request.GET.get('estado', '')
        plan_id = request.GET.get('plan_id', '')
        provincia = request.GET.get('provincia', '')
        dias_str = request.GET.get('dias', '')

        def _cutoff(dias_str):
            try:
                return timezone.now() - timedelta(days=int(dias_str))
            except (ValueError, TypeError):
                return None

        lc = cc = 0

        if tipo in ('leads', 'todos'):
            qs = Lead.objects.filter(telefono__startswith='+')
            if estado:
                qs = qs.filter(estado=estado)
            if plan_id:
                qs = qs.filter(plan_interes_id=plan_id)
            if provincia:
                qs = qs.filter(provincia__icontains=provincia)
            cutoff = _cutoff(dias_str)
            if cutoff:
                qs = qs.filter(updated_at__lt=cutoff)
            lc = qs.count()

        if tipo in ('clientes', 'todos'):
            qs = Cliente.objects.filter(telefono__startswith='+')
            if plan_id:
                qs = qs.filter(plan_id=plan_id)
            if provincia:
                qs = qs.filter(provincia__icontains=provincia)
            cutoff = _cutoff(dias_str)
            if cutoff:
                qs = qs.filter(updated_at__lt=cutoff)
            cc = qs.count()

        return JsonResponse({'total': lc + cc, 'leads': lc, 'clientes': cc})


def _get_extra_keys_json():
    from apps.leads.models import Lead
    keys = set()
    for lead in Lead.objects.exclude(datos_extra={}).values_list('datos_extra', flat=True):
        if isinstance(lead, dict):
            keys.update(lead.keys())
    return json.dumps(sorted(keys))


class CampanaListView(LoginRequiredMixin, SupervisorRequiredMixin, ListView):
    model = Campana
    template_name = 'campaigns/campana_list.html'
    context_object_name = 'campanas'
    paginate_by = 25


class CampanaCreateView(LoginRequiredMixin, SupervisorRequiredMixin, View):
    template_name = 'campaigns/campana_form.html'

    def _plantillas_data(self):
        from apps.whatsapp.models import PlantillaHSM
        data = {}
        for p in PlantillaHSM.objects.filter(activa=True):
            data[str(p.pk)] = {
                'nombre': p.nombre,
                'cuerpoRaw': p.cuerpo,
                'variables': p.variables or [],
                'header_tipo': p.header_tipo,
                'header_contenido': p.header_contenido,
                'footer': p.footer,
                'botones': p.botones or [],
            }
        return data

    def _ctx(self, form):
        from apps.leads.models import Plan
        return {
            'form': form,
            'plantillas_data': self._plantillas_data(),
            'extra_keys_json': _get_extra_keys_json(),
            'planes': list(Plan.objects.filter(activo=True).values('id', 'nombre')),
        }

    def get(self, request):
        return render(request, self.template_name, self._ctx(CampanaForm()))

    def post(self, request):
        form = CampanaForm(request.POST)
        if form.is_valid():
            campana = form.save(commit=False)
            campana.creado_por = request.user
            campana.status = Campana.STATUS_BORRADOR
            campana.save()
            counts = campana.get_recipients_count()
            campana.total_destinatarios = counts['total']
            campana.save(update_fields=['total_destinatarios'])
            messages.success(request, f'Campaña creada. Destinatarios: {counts["total"]} ({counts["leads"]} leads, {counts["clientes"]} clientes).')
            return redirect('campaigns:detail', pk=campana.pk)
        return render(request, self.template_name, self._ctx(form))


class CampanaDetailView(LoginRequiredMixin, SupervisorRequiredMixin, DetailView):
    model = Campana
    template_name = 'campaigns/campana_detail.html'
    context_object_name = 'campana'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        logs = self.object.logs.select_related('lead', 'cliente').order_by('-created_at')
        paginator = Paginator(logs, 25)
        ctx['logs'] = paginator.get_page(self.request.GET.get('page'))
        ctx['destinatarios_preview'] = self.object.get_recipients_count()
        return ctx


class CampanaLanzarView(LoginRequiredMixin, SupervisorRequiredMixin, View):
    def post(self, request, pk):
        campana = get_object_or_404(Campana, pk=pk, status__in=[Campana.STATUS_BORRADOR, Campana.STATUS_PROGRAMADA])
        campana.status = Campana.STATUS_PROGRAMADA
        campana.save(update_fields=['status'])
        ejecutar_campana.delay(campana.pk)
        messages.success(request, f'Campaña "{campana.nombre}" lanzada.')
        return redirect('campaigns:detail', pk=pk)


class CampanaDeleteView(LoginRequiredMixin, SupervisorRequiredMixin, DeleteView):
    model = Campana
    template_name = 'campaigns/campana_confirm_delete.html'
    success_url = reverse_lazy('campaigns:list')

    def get_queryset(self):
        return super().get_queryset().filter(status=Campana.STATUS_BORRADOR)
