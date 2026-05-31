import csv
import io
import json
import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, DeleteView
from django.urls import reverse_lazy

from apps.leads.models import CampoPersonalizado, Plan
from utils.dynamic_filter import apply_dynamic_filters, fields_for_js, _cliente_fields
from .forms import ClienteForm, ClienteImportForm
from .models import Cliente


class ClienteListView(LoginRequiredMixin, View):
    template_name = 'clientes/cliente_list.html'

    def get(self, request):
        qs = Cliente.objects.select_related('plan', 'agente')

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre_completo__icontains=q) |
                Q(dni__icontains=q) |
                Q(telefono__icontains=q) |
                Q(email__icontains=q) |
                Q(numero_afiliado__icontains=q)
            )

        field_defs = _cliente_fields()
        qs = apply_dynamic_filters(qs, request, field_defs)

        total = qs.count()
        paginator = Paginator(qs, 25)
        page = paginator.get_page(request.GET.get('page'))

        active_filters = list(zip(
            request.GET.getlist('fc'),
            request.GET.getlist('fo'),
            request.GET.getlist('fv'),
        ))

        return render(request, self.template_name, {
            'clientes':       page,
            'total':          total,
            'q':              q,
            'active_filters': active_filters,
            'filter_fields':  json.dumps(fields_for_js(field_defs, request.user), ensure_ascii=False),
            'is_paginated':   page.has_other_pages(),
            'page_obj':       page,
            'paginator':      paginator,
        })


class ClienteDetailView(LoginRequiredMixin, DetailView):
    model = Cliente
    template_name = 'clientes/cliente_detail.html'
    context_object_name = 'cliente'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['campos'] = CampoPersonalizado.objects.filter(
            activo=True,
            alcance__in=[CampoPersonalizado.ALCANCE_CLIENTES, CampoPersonalizado.ALCANCE_AMBOS]
        )
        ctx['tareas'] = self.object.tareas.select_related('agente').order_by('-fecha_programada')[:10]
        return ctx

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        if request.POST.get('action') == 'save_campos':
            campos = CampoPersonalizado.objects.filter(
                activo=True,
                alcance__in=[CampoPersonalizado.ALCANCE_CLIENTES, CampoPersonalizado.ALCANCE_AMBOS]
            )
            extra = dict(cliente.datos_extra or {})
            for campo in campos:
                if campo.tipo == CampoPersonalizado.TIPO_BOOLEANO:
                    extra[campo.slug] = bool(request.POST.get(f'campo_{campo.slug}'))
                else:
                    val = request.POST.get(f'campo_{campo.slug}', '').strip()
                    if val:
                        extra[campo.slug] = val
                    else:
                        extra.pop(campo.slug, None)
            cliente.datos_extra = extra
            cliente.save(update_fields=['datos_extra'])
            messages.success(request, 'Campos guardados.')
        return redirect('clientes:detail', pk=pk)


class ClienteCreateView(LoginRequiredMixin, View):
    template_name = 'clientes/cliente_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ClienteForm(user=request.user)})

    def post(self, request):
        form = ClienteForm(request.POST, user=request.user)
        if form.is_valid():
            cliente = form.save(commit=False)
            if not cliente.agente and not request.user.can_see_all_leads:
                cliente.agente = request.user
            cliente.save()
            messages.success(request, 'Cliente creado correctamente.')
            return redirect('clientes:detail', pk=cliente.pk)
        return render(request, self.template_name, {'form': form})


class ClienteUpdateView(LoginRequiredMixin, View):
    template_name = 'clientes/cliente_form.html'

    def get(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        return render(request, self.template_name, {'form': ClienteForm(instance=cliente, user=request.user), 'cliente': cliente})

    def post(self, request, pk):
        cliente = get_object_or_404(Cliente, pk=pk)
        form = ClienteForm(request.POST, instance=cliente, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente actualizado.')
            return redirect('clientes:detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'cliente': cliente})


class ClienteDeleteView(LoginRequiredMixin, DeleteView):
    model = Cliente
    template_name = 'clientes/cliente_confirm_delete.html'
    success_url = reverse_lazy('clientes:list')


# ── Helpers para importación ──────────────────────────────

def _read_cliente_file(archivo):
    name = archivo.name.lower()
    if name.endswith('.xlsx') or name.endswith('.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return [], []
        headers = [str(h).strip() if h is not None else f'col_{i}' for i, h in enumerate(all_rows[0])]
        rows = []
        for raw in all_rows[1:]:
            if all(v is None or str(v).strip() == '' for v in raw):
                continue
            rows.append({headers[i]: (str(raw[i]).strip() if raw[i] is not None else '') for i in range(len(headers))})
        return headers, rows
    else:
        try:
            content = archivo.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            archivo.seek(0)
            content = archivo.read().decode('latin-1')
        reader = csv.DictReader(io.StringIO(content))
        headers = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader if any(v.strip() for v in r.values())]
        return headers, rows


def _get_c(row_lower, *keys, default=''):
    for k in keys:
        v = row_lower.get(k.lower(), '')
        if v and str(v).strip():
            return str(v).strip()
    return default


def _process_cliente_row(row, plans_by_name, actualizar):
    row_lower = {k.lower().strip(): v for k, v in row.items()}

    nombre = _get_c(row_lower, 'nombre_completo', 'nombre', 'name', 'full_name')
    if not nombre:
        return 'error', 'Nombre vacío'

    raw_dni = re.sub(r'\D', '', _get_c(row_lower, 'dni', 'documento', 'cedula', 'rut'))
    dni = raw_dni[:20] if raw_dni else ''

    telefono = _get_c(row_lower, 'telefono', 'phone', 'tel', 'celular')
    email = _get_c(row_lower, 'email', 'correo', 'mail')
    localidad = _get_c(row_lower, 'localidad', 'ciudad', 'city')
    provincia = _get_c(row_lower, 'provincia', 'province', 'region')
    notas = _get_c(row_lower, 'notas', 'notes', 'observaciones')
    numero_afiliado = _get_c(row_lower, 'numero_afiliado', 'afiliado', 'nro_afiliado', 'n_afiliado')
    plan_nombre = _get_c(row_lower, 'plan', 'plan_nombre')
    grupo_raw = _get_c(row_lower, 'grupo_familiar', 'grupo')
    try:
        grupo_familiar = max(1, int(grupo_raw))
    except (ValueError, TypeError):
        grupo_familiar = 1

    plan = plans_by_name.get(plan_nombre.lower()) if plan_nombre else None

    if not dni and not telefono:
        return 'error', 'Se requiere DNI o teléfono para identificar al cliente'

    # Duplicate lookup: DNI first, then phone
    existing = None
    if dni:
        existing = Cliente.objects.filter(dni=dni).first()
    if not existing and telefono:
        existing = Cliente.objects.filter(telefono=telefono).first()

    if existing:
        if not actualizar:
            return 'skipped', ''
        updated = []
        if not existing.nombre_completo and nombre:
            existing.nombre_completo = nombre; updated.append('nombre_completo')
        if not existing.telefono and telefono:
            existing.telefono = telefono; updated.append('telefono')
        if not existing.dni and dni:
            existing.dni = dni; updated.append('dni')
        if not existing.email and email:
            existing.email = email; updated.append('email')
        if not existing.localidad and localidad:
            existing.localidad = localidad; updated.append('localidad')
        if not existing.provincia and provincia:
            existing.provincia = provincia; updated.append('provincia')
        if not existing.notas and notas:
            existing.notas = notas; updated.append('notas')
        if not existing.numero_afiliado and numero_afiliado:
            existing.numero_afiliado = numero_afiliado; updated.append('numero_afiliado')
        if plan and not existing.plan:
            existing.plan = plan; updated.append('plan')
        if updated:
            existing.save(update_fields=updated + ['updated_at'])
            return 'updated', ''
        return 'skipped', ''

    Cliente.objects.create(
        nombre_completo=nombre,
        dni=dni,
        telefono=telefono,
        email=email,
        localidad=localidad,
        provincia=provincia,
        notas=notas,
        plan=plan,
        numero_afiliado=numero_afiliado,
        grupo_familiar=grupo_familiar,
    )
    return 'created', ''


class ClienteImportView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'clientes/cliente_import.html'

    def test_func(self):
        return self.request.user.can_see_all_leads

    def get(self, request):
        return render(request, self.template_name, {'form': ClienteImportForm()})

    def post(self, request):
        form = ClienteImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        archivo = request.FILES['archivo']
        actualizar = form.cleaned_data.get('actualizar_existentes', True)

        try:
            headers, rows = _read_cliente_file(archivo)
        except Exception as e:
            messages.error(request, f'Error leyendo el archivo: {e}')
            return render(request, self.template_name, {'form': form})

        if not rows:
            messages.warning(request, 'El archivo está vacío o no tiene filas de datos.')
            return render(request, self.template_name, {'form': form})

        plans_by_name = {p.nombre.lower(): p for p in Plan.objects.filter(activo=True)}

        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'error': 0}
        errors = []

        for i, row in enumerate(rows, start=2):
            action, msg = _process_cliente_row(row, plans_by_name, actualizar)
            stats[action] += 1
            if action == 'error':
                errors.append({'fila': i, 'msg': msg, 'datos': str(row)[:120]})

        return render(request, self.template_name, {
            'form': ClienteImportForm(),
            'resultado': True,
            'stats': stats,
            'errors': errors[:50],
            'total_filas': len(rows),
        })
