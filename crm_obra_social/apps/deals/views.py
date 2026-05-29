import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.clientes.models import Cliente
from apps.leads.models import Lead
from apps.users.models import User
from .models import Pipeline, PipelineStage, Deal, DealHistory

logger = logging.getLogger('apps.deals')


class SupervisorMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


# ─── Kanban ────────────────────────────────────────────────────────────────

class DealKanbanView(LoginRequiredMixin, View):
    template_name = 'deals/kanban.html'

    def get(self, request):
        pipelines = Pipeline.objects.prefetch_related('stages').order_by('-activo', 'nombre')
        if not pipelines.exists():
            return render(request, self.template_name, {'no_pipelines': True, 'pipelines': []})

        pipeline_id = request.GET.get('pipeline')
        pipeline = None
        if pipeline_id:
            pipeline = pipelines.filter(pk=pipeline_id).first()
        if not pipeline:
            pipeline = pipelines.first()

        stages = pipeline.stages.all()
        deals_qs = Deal.objects.filter(pipeline=pipeline).select_related(
            'lead', 'cliente', 'agente', 'stage'
        )

        columns = {}
        for stage in stages:
            columns[stage.pk] = {
                'stage': stage,
                'deals': [],
            }
        for deal in deals_qs:
            if deal.stage_id in columns:
                columns[deal.stage_id]['deals'].append(deal)

        return render(request, self.template_name, {
            'pipeline':  pipeline,
            'pipelines': pipelines,
            'columns':   list(columns.values()),
        })


# ─── Deal list ──────────────────────────────────────────────────────────────

class DealListView(LoginRequiredMixin, View):
    template_name = 'deals/list.html'

    def get(self, request):
        pipelines = Pipeline.objects.all().order_by('-activo', 'nombre')
        qs = Deal.objects.select_related('pipeline', 'stage', 'lead', 'cliente', 'agente')

        pipeline_id = request.GET.get('pipeline')
        stage_id    = request.GET.get('stage')
        agente_id   = request.GET.get('agente')
        q           = request.GET.get('q', '').strip()

        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)
        if stage_id:
            qs = qs.filter(stage_id=stage_id)
        if agente_id:
            qs = qs.filter(agente_id=agente_id)
        if q:
            qs = qs.filter(
                Q(titulo__icontains=q) |
                Q(nombre_contacto__icontains=q) |
                Q(lead__nombre_completo__icontains=q) |
                Q(cliente__nombre_completo__icontains=q)
            )

        total_valor = qs.aggregate(t=Sum('valor'))['t'] or 0

        return render(request, self.template_name, {
            'deals':       qs,
            'pipelines':   pipelines,
            'agentes':     User.objects.filter(is_active=True).order_by('first_name'),
            'total_valor': total_valor,
            'filtros': {
                'pipeline': pipeline_id or '',
                'stage':    stage_id or '',
                'agente':   agente_id or '',
                'q':        q,
            },
        })


# ─── Deal CRUD ──────────────────────────────────────────────────────────────

class DealCreateView(LoginRequiredMixin, View):
    template_name = 'deals/deal_form.html'

    def get(self, request):
        pipeline_id = request.GET.get('pipeline')
        lead_id     = request.GET.get('lead')
        cliente_id  = request.GET.get('cliente')
        pipeline    = None
        lead        = None
        cliente     = None
        if pipeline_id:
            pipeline = Pipeline.objects.filter(pk=pipeline_id).first()
        if not pipeline:
            pipeline = Pipeline.objects.order_by('-activo', 'nombre').first()
        if lead_id:
            lead = Lead.objects.filter(pk=lead_id).first()
        if cliente_id:
            cliente = Cliente.objects.filter(pk=cliente_id).first()
        return render(request, self.template_name, _deal_form_ctx(request, None, pipeline, lead, cliente))

    def post(self, request):
        err, deal = _save_deal(request.POST, None, request.user)
        if err:
            messages.error(request, err)
            pipeline_id = request.POST.get('pipeline')
            pipeline = Pipeline.objects.filter(pk=pipeline_id).first() if pipeline_id else None
            return render(request, self.template_name, _deal_form_ctx(request, None, pipeline, None))
        messages.success(request, 'Negociación creada.')
        return redirect('deals:kanban')


class DealUpdateView(LoginRequiredMixin, View):
    template_name = 'deals/deal_form.html'

    def get(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        return render(request, self.template_name, _deal_form_ctx(
            request, deal, deal.pipeline, deal.lead,
            deal.cliente if deal.cliente_id else None,
        ))

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        err, deal = _save_deal(request.POST, deal, request.user)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, _deal_form_ctx(request, deal, deal.pipeline, deal.lead))
        messages.success(request, 'Negociación actualizada.')
        return redirect('deals:kanban')


class DealDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        deal.delete()
        messages.success(request, 'Negociación eliminada.')
        return redirect('deals:kanban')


class DealDetailView(LoginRequiredMixin, View):
    template_name = 'deals/deal_detail.html'

    def get(self, request, pk):
        deal = get_object_or_404(
            Deal.objects.select_related('pipeline', 'stage', 'lead', 'cliente', 'agente'),
            pk=pk,
        )
        historial = deal.history.select_related('stage_anterior', 'stage_nuevo', 'cambiado_por')
        return render(request, self.template_name, {'deal': deal, 'historial': historial})


# ─── Deal move (AJAX Kanban drag & drop) ───────────────────────────────────

class DealMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        stage_id = request.POST.get('stage_id')
        try:
            stage = PipelineStage.objects.get(pk=stage_id, pipeline=deal.pipeline)
        except PipelineStage.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Etapa inválida'}, status=400)

        deal._cambiado_por = request.user
        deal.stage = stage
        deal.save(update_fields=['stage', 'updated_at'])
        return JsonResponse({'ok': True, 'stage_id': stage.pk, 'stage_nombre': stage.nombre})


# ─── Contact search API (Lead + Cliente) ───────────────────────────────────

class ContactoSearchAPIView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return JsonResponse({'results': []})

        results = []
        leads = Lead.objects.filter(
            Q(nombre_completo__icontains=q) | Q(telefono__icontains=q) | Q(dni__icontains=q)
        ).values('pk', 'nombre_completo', 'telefono')[:10]
        for l in leads:
            results.append({
                'id': l['pk'], 'tipo': 'lead',
                'nombre': l['nombre_completo'], 'telefono': l['telefono'] or '',
            })

        clientes = Cliente.objects.filter(
            Q(nombre_completo__icontains=q) | Q(telefono__icontains=q) | Q(dni__icontains=q)
        ).values('pk', 'nombre_completo', 'telefono')[:10]
        for c in clientes:
            results.append({
                'id': c['pk'], 'tipo': 'cliente',
                'nombre': c['nombre_completo'], 'telefono': c['telefono'] or '',
            })

        return JsonResponse({'results': results})


# ─── Pipeline management ────────────────────────────────────────────────────

class PipelineListView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'deals/pipeline_list.html'

    def get(self, request):
        pipelines = Pipeline.objects.prefetch_related('stages').annotate(
            deal_count=Count('deals'),
        )
        return render(request, self.template_name, {'pipelines': pipelines})


_DEFAULT_STAGES = [
    ('Nuevo', 'secondary'),
    ('En contacto', 'info'),
    ('Propuesta enviada', 'primary'),
    ('Negociando', 'warning'),
    ('Ganado', 'success'),
    ('Perdido', 'danger'),
]


class PipelineCreateView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'deals/pipeline_form.html'

    def get(self, request):
        return render(request, self.template_name, {'pipeline': None, 'default_stages': _DEFAULT_STAGES})

    def post(self, request):
        err, pipeline = _save_pipeline(request.POST, None)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, {'pipeline': None, 'data': request.POST})
        _save_stages(request.POST, pipeline)
        messages.success(request, 'Pipeline creado.')
        return redirect('deals:pipeline_list')


class PipelineUpdateView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'deals/pipeline_form.html'

    def get(self, request, pk):
        pipeline = get_object_or_404(Pipeline, pk=pk)
        return render(request, self.template_name, {
            'pipeline': pipeline,
            'stages': pipeline.stages.all(),
        })

    def post(self, request, pk):
        pipeline = get_object_or_404(Pipeline, pk=pk)
        err, pipeline = _save_pipeline(request.POST, pipeline)
        if err:
            messages.error(request, err)
            return render(request, self.template_name, {
                'pipeline': pipeline, 'stages': pipeline.stages.all(), 'data': request.POST,
            })
        _save_stages(request.POST, pipeline)
        messages.success(request, 'Pipeline actualizado.')
        return redirect('deals:pipeline_list')


class PipelineDeleteView(LoginRequiredMixin, SupervisorMixin, View):
    def post(self, request, pk):
        pipeline = get_object_or_404(Pipeline, pk=pk)
        if pipeline.deals.exists():
            messages.error(request, 'No se puede eliminar: hay negociaciones en este pipeline.')
            return redirect('deals:pipeline_list')
        pipeline.delete()
        messages.success(request, 'Pipeline eliminado.')
        return redirect('deals:pipeline_list')


# ─── Stage AJAX (reorder + delete) ─────────────────────────────────────────

class StageDeleteView(LoginRequiredMixin, SupervisorMixin, View):
    def post(self, request, pk):
        stage = get_object_or_404(PipelineStage, pk=pk)
        if stage.deals.exists():
            messages.error(request, f'La etapa "{stage.nombre}" tiene negociaciones — movelas primero.')
            return redirect('deals:pipeline_update', pk=stage.pipeline_id)
        pipeline_pk = stage.pipeline_id
        stage.delete()
        messages.success(request, 'Etapa eliminada.')
        return redirect('deals:pipeline_update', pk=pipeline_pk)


# ─── API: stages by pipeline (for deal form select) ─────────────────────────

class StagesAPIView(LoginRequiredMixin, View):
    def get(self, request, pipeline_pk):
        stages = PipelineStage.objects.filter(pipeline_id=pipeline_pk).order_by('orden', 'nombre').values('id', 'nombre', 'color')
        return JsonResponse({'stages': list(stages)})


# ─── Helpers ────────────────────────────────────────────────────────────────

def _deal_form_ctx(request, deal, pipeline, lead, cliente=None):
    pipelines = Pipeline.objects.all().prefetch_related('stages').order_by('-activo', 'nombre')
    return {
        'deal':      deal,
        'pipeline':  pipeline,
        'lead':      lead,
        'cliente':   cliente,
        'pipelines': pipelines,
        'agentes':   User.objects.filter(is_active=True).order_by('first_name', 'last_name'),
        'data':      request.POST if request.method == 'POST' else {},
    }


def _save_deal(data, instance, user):
    titulo = data.get('titulo', '').strip()
    if not titulo:
        return 'El título es requerido.', instance

    pipeline_id = data.get('pipeline')
    stage_id    = data.get('stage')
    try:
        pipeline = Pipeline.objects.get(pk=pipeline_id)
        stage    = PipelineStage.objects.get(pk=stage_id, pipeline=pipeline)
    except (Pipeline.DoesNotExist, PipelineStage.DoesNotExist, TypeError, ValueError):
        return 'Pipeline o etapa inválidos.', instance

    valor = None
    valor_raw = data.get('valor', '').strip()
    if valor_raw:
        try:
            valor = Decimal(valor_raw.replace(',', '.'))
        except InvalidOperation:
            return 'El valor debe ser un número válido.', instance

    if instance is None:
        instance = Deal()

    instance.titulo   = titulo
    instance.pipeline = pipeline
    instance.stage    = stage
    instance.valor    = valor
    instance.descripcion           = data.get('descripcion', '').strip()
    instance.nombre_contacto       = data.get('nombre_contacto', '').strip()
    instance.fecha_cierre_estimada = data.get('fecha_cierre_estimada') or None

    # Contact: lead or cliente (mutually exclusive)
    lead_id    = data.get('lead_id', '').strip()
    cliente_id = data.get('cliente_id', '').strip()
    instance.lead    = None
    instance.cliente = None
    if lead_id:
        instance.lead = Lead.objects.filter(pk=lead_id).first()
        if instance.lead and not instance.nombre_contacto:
            instance.nombre_contacto = instance.lead.nombre_completo
    elif cliente_id:
        instance.cliente = Cliente.objects.filter(pk=cliente_id).first()
        if instance.cliente and not instance.nombre_contacto:
            instance.nombre_contacto = instance.cliente.nombre_completo

    agente_id = data.get('agente')
    if agente_id:
        instance.agente = User.objects.filter(pk=agente_id).first()
    else:
        instance.agente = user if not instance.pk else instance.agente

    instance._cambiado_por = user
    instance.save()
    return None, instance


def _save_pipeline(data, instance):
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return 'El nombre es requerido.', instance
    if instance is None:
        instance = Pipeline()
    instance.nombre      = nombre
    instance.descripcion = data.get('descripcion', '').strip()
    instance.activo      = data.get('activa') == 'on'
    instance.save()
    return None, instance


def _save_stages(data, pipeline):
    """Process inline stage form: stage_nombre[], stage_color[], stage_orden[], stage_id[]."""
    nombres  = data.getlist('stage_nombre')
    colores  = data.getlist('stage_color')
    ordenes  = data.getlist('stage_orden')
    ids      = data.getlist('stage_id')
    deletes  = {d for d in data.getlist('stage_delete') if d}

    kept_ids = set()
    for i, nombre in enumerate(nombres):
        nombre = nombre.strip()
        if not nombre:
            continue
        stage_id = ids[i] if i < len(ids) else ''
        color    = colores[i] if i < len(colores) else 'primary'
        try:
            orden = int(ordenes[i]) if i < len(ordenes) else i
        except (ValueError, TypeError):
            orden = i

        if stage_id and stage_id not in deletes:
            stage = PipelineStage.objects.filter(pk=stage_id, pipeline=pipeline).first()
            if stage:
                stage.nombre = nombre
                stage.color  = color
                stage.orden  = orden
                stage.save()
                kept_ids.add(stage.pk)
        elif not stage_id:
            stage = PipelineStage.objects.create(
                pipeline=pipeline, nombre=nombre, color=color, orden=orden,
            )
            kept_ids.add(stage.pk)

    # Delete stages marked for deletion (only if no deals)
    for del_id in deletes:
        stage = PipelineStage.objects.filter(pk=del_id, pipeline=pipeline).first()
        if stage and not stage.deals.exists():
            stage.delete()
