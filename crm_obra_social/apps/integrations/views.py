import json
import logging
import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import ApiKey, WebhookLog

logger = logging.getLogger('apps.integrations')


# ─── Auth decorator ───────────────────────────────────────────────────────────

def _get_api_key(request) -> ApiKey | None:
    raw = (
        request.headers.get('X-API-Key')
        or request.GET.get('api_key')
        or request.POST.get('api_key')
    )
    if not raw:
        return None
    try:
        import uuid
        key_uuid = uuid.UUID(str(raw))
        return ApiKey.objects.filter(key=key_uuid, activa=True).first()
    except (ValueError, AttributeError):
        return None


def _log_request(api_key, endpoint, method, request, response_status, response_body, lead=None, status='ok'):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    try:
        WebhookLog.objects.create(
            api_key=api_key,
            endpoint=endpoint,
            method=method,
            ip=ip or None,
            request_body=request.body.decode('utf-8', errors='replace')[:5000],
            response_status=response_status,
            response_body=json.dumps(response_body)[:2000],
            status=status,
            lead_creado=lead,
        )
        if api_key:
            ApiKey.objects.filter(pk=api_key.pk).update(
                ultimo_uso_at=timezone.now(),
                total_usos=api_key.total_usos + 1,
            )
    except Exception:
        pass


# ─── Public API endpoints ─────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class LeadCreateAPIView(View):
    """
    POST /api/v1/leads/
    Creates a lead from an external source (web form, landing page, etc.).
    Requires X-API-Key header.

    Body (JSON or form-data):
    {
        "nombre_completo": "Juan Pérez",    // required
        "telefono": "+541123456789",        // required
        "codigo_pais": "54",               // optional, used if telefono has no +
        "email": "juan@example.com",
        "dni": "35123456",
        "localidad": "Buenos Aires",
        "provincia": "Buenos Aires",
        "plan": "Individual",
        "notas": "Interesado por Google Ads",
        "origen": "web",
        "datos_extra": {"utm_source": "google", "utm_campaign": "marca"}
    }
    """

    def post(self, request):
        api_key = _get_api_key(request)
        if not api_key:
            resp = {'error': 'API key inválida o ausente', 'code': 'unauthorized'}
            _log_request(None, '/api/v1/leads/', 'POST', request, 401, resp, status='error')
            return JsonResponse(resp, status=401)

        try:
            if request.content_type and 'application/json' in request.content_type:
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
        except (json.JSONDecodeError, Exception):
            resp = {'error': 'Body inválido', 'code': 'bad_request'}
            _log_request(api_key, '/api/v1/leads/', 'POST', request, 400, resp, status='error')
            return JsonResponse(resp, status=400)

        nombre = str(data.get('nombre_completo') or data.get('nombre') or data.get('name') or '').strip()
        if not nombre:
            resp = {'error': 'nombre_completo es requerido', 'code': 'validation_error'}
            _log_request(api_key, '/api/v1/leads/', 'POST', request, 422, resp, status='error')
            return JsonResponse(resp, status=422)

        raw_phone = str(data.get('telefono') or data.get('phone') or '').strip()
        codigo_pais = str(data.get('codigo_pais') or data.get('country_code') or '54').strip()
        phone = _normalize_phone(raw_phone, codigo_pais)
        if not phone:
            resp = {'error': f'Teléfono inválido: {raw_phone!r}', 'code': 'validation_error'}
            _log_request(api_key, '/api/v1/leads/', 'POST', request, 422, resp, status='error')
            return JsonResponse(resp, status=422)

        from apps.leads.models import Lead, HistorialEstado, Plan

        # Look up plan
        plan_nombre = str(data.get('plan') or '').strip()
        plan = Plan.objects.filter(nombre__iexact=plan_nombre).first() if plan_nombre else None

        # datos_extra — any unknown fields + explicit datos_extra dict
        known = {'nombre_completo', 'nombre', 'name', 'telefono', 'phone', 'codigo_pais',
                 'country_code', 'email', 'dni', 'localidad', 'provincia', 'plan', 'notas',
                 'origen', 'datos_extra', 'api_key'}
        datos_extra = {k: str(v) for k, v in data.items() if k not in known and v}
        if isinstance(data.get('datos_extra'), dict):
            datos_extra.update(data['datos_extra'])

        existing = Lead.objects.filter(telefono=phone).first()
        if existing:
            # Update datos_extra and empty fields
            updated = []
            if not existing.email and data.get('email'):
                existing.email = str(data['email']).strip(); updated.append('email')
            if not existing.notas and data.get('notas'):
                existing.notas = str(data['notas']).strip(); updated.append('notas')
            if datos_extra:
                current = existing.datos_extra or {}
                current.update(datos_extra)
                existing.datos_extra = current; updated.append('datos_extra')
            if updated:
                existing.save(update_fields=updated + ['updated_at'])
            resp = {'status': 'updated', 'lead_id': existing.pk, 'telefono': phone}
            _log_request(api_key, '/api/v1/leads/', 'POST', request, 200, resp, lead=existing)
            return JsonResponse(resp, status=200)

        dni_raw = re.sub(r'\D', '', str(data.get('dni') or ''))
        dni = (dni_raw[:8] or '0000000').zfill(7)

        origen_raw = str(data.get('origen') or api_key.origen_default or 'web').strip()
        origen_map = {
            'web': Lead.ORIGEN_WEB, 'campana': Lead.ORIGEN_CAMPANA, 'campaña': Lead.ORIGEN_CAMPANA,
            'referido': Lead.ORIGEN_REFERIDO, 'llamada': Lead.ORIGEN_LLAMADA, 'whatsapp': Lead.ORIGEN_WHATSAPP,
        }
        origen = origen_map.get(origen_raw.lower(), Lead.ORIGEN_WEB)

        lead = Lead.objects.create(
            nombre_completo=nombre,
            dni=dni,
            telefono=phone,
            email=str(data.get('email') or '').strip(),
            localidad=str(data.get('localidad') or '').strip(),
            provincia=str(data.get('provincia') or '').strip(),
            notas=str(data.get('notas') or '').strip(),
            origen=origen,
            plan_interes=plan,
            agente=api_key.agente_default,
            estado=api_key.estado_inicial or Lead.ESTADO_NUEVO,
            datos_extra=datos_extra,
        )
        HistorialEstado.objects.create(
            lead=lead,
            estado_nuevo=lead.estado,
            nota=f'Lead creado vía API ({api_key.nombre})',
        )

        resp = {'status': 'created', 'lead_id': lead.pk, 'telefono': phone}
        _log_request(api_key, '/api/v1/leads/', 'POST', request, 201, resp, lead=lead)
        return JsonResponse(resp, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class LeadUpdateAPIView(View):
    """
    POST /api/v1/leads/actualizar/
    Update lead fields by phone number. Designed for n8n/chatbot flows.

    Body (JSON):
    {
        "telefono": "+541123456789",   // required — used to find the lead
        "nombre_completo": "...",      // optional
        "email": "...",
        "dni": "...",
        "localidad": "...",
        "provincia": "...",
        "notas": "...",
        "plan": "Individual",          // plan name
        "estado": "interesado",        // nuevo|contactado|interesado|doc_pendiente|en_revision|afiliado|perdido
        "prioridad": "alta",           // alta|media|baja
        "datos_extra": {"clave": "valor"},  // merged into datos_extra
        "cualquier_otro_campo": "..."  // saved in datos_extra automatically
    }
    """

    def post(self, request):
        api_key = _get_api_key(request)
        if not api_key:
            return JsonResponse({'error': 'unauthorized'}, status=401)

        try:
            data = json.loads(request.body) if 'application/json' in (request.content_type or '') else request.POST.dict()
        except Exception:
            return JsonResponse({'error': 'bad_request'}, status=400)

        raw_phone = str(data.get('telefono') or data.get('phone') or '').strip()
        phone = _normalize_phone(raw_phone)
        if not phone:
            return JsonResponse({'error': 'telefono requerido', 'code': 'validation_error'}, status=422)

        from apps.leads.models import Lead, Plan

        lead = Lead.objects.filter(telefono=phone).first()
        if not lead:
            return JsonResponse({'error': 'lead_not_found', 'telefono': phone}, status=404)

        updated = []

        DIRECT_FIELDS = ('nombre_completo', 'email', 'localidad', 'provincia', 'notas')
        for field in DIRECT_FIELDS:
            val = str(data.get(field) or '').strip()
            if val:
                setattr(lead, field, val)
                updated.append(field)

        if data.get('dni'):
            import re as _re
            dni_clean = _re.sub(r'\D', '', str(data['dni']))[:8]
            if dni_clean:
                lead.dni = dni_clean
                updated.append('dni')

        if data.get('plan'):
            plan = Plan.objects.filter(nombre__iexact=str(data['plan']).strip()).first()
            if plan:
                lead.plan_interes = plan
                updated.append('plan_interes')

        if data.get('estado'):
            estado_val = str(data['estado']).strip().lower()
            valid_estados = [e[0] for e in Lead.ESTADO_CHOICES]
            if estado_val in valid_estados:
                lead.estado = estado_val
                updated.append('estado')

        if data.get('prioridad'):
            prio_val = str(data['prioridad']).strip().lower()
            valid_prios = [p[0] for p in Lead.PRIORIDAD_CHOICES]
            if prio_val in valid_prios:
                lead.prioridad = prio_val
                updated.append('prioridad')

        # datos_extra: merge explicit dict + any unknown keys
        known = {
            'telefono', 'phone', 'nombre_completo', 'email', 'dni', 'localidad',
            'provincia', 'notas', 'plan', 'estado', 'prioridad', 'datos_extra', 'api_key',
        }
        extra_updates = {k: str(v) for k, v in data.items() if k not in known and str(v).strip()}
        if isinstance(data.get('datos_extra'), dict):
            extra_updates.update({k: str(v) for k, v in data['datos_extra'].items() if str(v).strip()})

        if extra_updates:
            current = lead.datos_extra or {}
            current.update(extra_updates)
            lead.datos_extra = current
            if 'datos_extra' not in updated:
                updated.append('datos_extra')

        if updated:
            lead.save(update_fields=updated + ['updated_at'])

        resp = {
            'status': 'updated',
            'lead_id': lead.pk,
            'telefono': lead.telefono,
            'campos_actualizados': updated,
        }
        _log_request(api_key, '/api/v1/leads/actualizar/', 'POST', request, 200, resp, lead=lead)
        return JsonResponse(resp)


@method_decorator(csrf_exempt, name='dispatch')
class LeadStatusAPIView(View):
    """GET /api/v1/leads/<pk>/ — returns lead status + datos_extra."""

    def get(self, request, pk):
        api_key = _get_api_key(request)
        if not api_key:
            return JsonResponse({'error': 'unauthorized'}, status=401)
        from apps.leads.models import Lead
        try:
            lead = Lead.objects.select_related('plan_interes', 'agente').get(pk=pk)
        except Lead.DoesNotExist:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse(_lead_to_dict(lead))


@method_decorator(csrf_exempt, name='dispatch')
class LeadSearchAPIView(View):
    """
    GET /api/v1/leads/buscar/?telefono=+541123456789
    Find a lead by phone number. Returns full data including datos_extra.
    Used by n8n to check conversation state (datos_extra.bot_step).
    """

    def get(self, request):
        api_key = _get_api_key(request)
        if not api_key:
            return JsonResponse({'error': 'unauthorized'}, status=401)

        raw_phone = request.GET.get('telefono') or request.GET.get('phone') or ''
        phone = _normalize_phone(raw_phone.strip())
        if not phone:
            return JsonResponse({'error': 'telefono requerido'}, status=422)

        from apps.leads.models import Lead
        lead = Lead.objects.select_related('plan_interes', 'agente').filter(telefono=phone).first()
        if not lead:
            return JsonResponse({'found': False, 'telefono': phone}, status=404)

        data = _lead_to_dict(lead)
        data['found'] = True
        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class GenericWebhookView(View):
    """
    POST /api/v1/webhook/<source>/
    Generic webhook endpoint. Creates a lead from the payload.
    Same authentication and field mapping as LeadCreateAPIView.
    """

    def post(self, request, source='generic'):
        api_key = _get_api_key(request)
        if not api_key:
            return JsonResponse({'error': 'unauthorized'}, status=401)

        try:
            if request.content_type and 'application/json' in request.content_type:
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
            data.setdefault('origen', source)
        except Exception:
            return JsonResponse({'error': 'bad_request'}, status=400)

        # Delegate to the same logic as LeadCreateAPIView
        request._body_override = json.dumps(data).encode()
        view = LeadCreateAPIView()
        view.request = request
        # Re-use by calling with modified data
        return _create_lead_from_data(api_key, data, request, f'/api/v1/webhook/{source}/')


def _create_lead_from_data(api_key, data, request, endpoint):
    """Shared lead creation logic for API and webhook views."""
    import re
    from apps.leads.models import Lead, HistorialEstado, Plan

    nombre = str(data.get('nombre_completo') or data.get('nombre') or data.get('name') or '').strip()
    if not nombre:
        return JsonResponse({'error': 'nombre_completo requerido'}, status=422)

    raw_phone = str(data.get('telefono') or data.get('phone') or '').strip()
    codigo_pais = str(data.get('codigo_pais') or '54')
    phone = _normalize_phone(raw_phone, codigo_pais)
    if not phone:
        resp = {'error': f'Teléfono inválido: {raw_phone!r}'}
        _log_request(api_key, endpoint, 'POST', request, 422, resp, status='error')
        return JsonResponse(resp, status=422)

    plan_nombre = str(data.get('plan') or '').strip()
    plan = Plan.objects.filter(nombre__iexact=plan_nombre).first() if plan_nombre else None

    known = {'nombre_completo', 'nombre', 'name', 'telefono', 'phone', 'codigo_pais',
             'email', 'dni', 'localidad', 'provincia', 'plan', 'notas', 'origen',
             'datos_extra', 'api_key', 'country_code'}
    datos_extra = {k: str(v) for k, v in data.items() if k not in known and v}
    if isinstance(data.get('datos_extra'), dict):
        datos_extra.update(data['datos_extra'])

    existing = Lead.objects.filter(telefono=phone).first()
    if existing:
        resp = {'status': 'existing', 'lead_id': existing.pk}
        _log_request(api_key, endpoint, 'POST', request, 200, resp, lead=existing)
        return JsonResponse(resp, status=200)

    dni_raw = re.sub(r'\D', '', str(data.get('dni') or ''))
    dni = (dni_raw[:8] or '0000000').zfill(7)
    origen_raw = str(data.get('origen') or api_key.origen_default or 'web').lower()
    origen_map = {
        'web': Lead.ORIGEN_WEB, 'campana': Lead.ORIGEN_CAMPANA, 'campaña': Lead.ORIGEN_CAMPANA,
        'referido': Lead.ORIGEN_REFERIDO, 'llamada': Lead.ORIGEN_LLAMADA, 'whatsapp': Lead.ORIGEN_WHATSAPP,
    }
    origen = origen_map.get(origen_raw, Lead.ORIGEN_WEB)

    lead = Lead.objects.create(
        nombre_completo=nombre, dni=dni, telefono=phone,
        email=str(data.get('email') or '').strip(),
        localidad=str(data.get('localidad') or '').strip(),
        provincia=str(data.get('provincia') or '').strip(),
        notas=str(data.get('notas') or '').strip(),
        origen=origen, plan_interes=plan,
        agente=api_key.agente_default,
        estado=api_key.estado_inicial or Lead.ESTADO_NUEVO,
        datos_extra=datos_extra,
    )
    HistorialEstado.objects.create(
        lead=lead, estado_nuevo=lead.estado,
        nota=f'Lead creado vía webhook ({api_key.nombre})',
    )
    resp = {'status': 'created', 'lead_id': lead.pk}
    _log_request(api_key, endpoint, 'POST', request, 201, resp, lead=lead)
    return JsonResponse(resp, status=201)


def _lead_to_dict(lead) -> dict:
    """Serialize a Lead to a dict for API responses."""
    return {
        'lead_id':        lead.pk,
        'nombre_completo':lead.nombre_completo,
        'telefono':       lead.telefono,
        'email':          lead.email,
        'dni':            lead.dni,
        'localidad':      lead.localidad,
        'provincia':      lead.provincia,
        'plan':           str(lead.plan_interes) if lead.plan_interes else None,
        'estado':         lead.estado,
        'estado_display': lead.get_estado_display(),
        'prioridad':      lead.prioridad,
        'agente':         lead.agente.get_full_name() if lead.agente else None,
        'datos_extra':    lead.datos_extra or {},
        'created_at':     lead.created_at.isoformat(),
        'updated_at':     lead.updated_at.isoformat(),
    }


def _normalize_phone(raw: str, codigo_pais: str = '54') -> str:
    cleaned = re.sub(r'[^\d+]', '', str(raw)).strip()
    if not cleaned:
        return ''
    if cleaned.startswith('+'):
        digits = re.sub(r'\D', '', cleaned)
    else:
        digits_stripped = cleaned.lstrip('0') or cleaned
        codigo = re.sub(r'\D', '', str(codigo_pais)).lstrip('0') or '54'
        # Avoid double-prepending if the number already includes the country code
        digits = digits_stripped if digits_stripped.startswith(codigo) else codigo + digits_stripped
    return ('+' + digits) if len(digits) >= 7 else ''


# ─── Admin UI views ────────────────────────────────────────────────────────────

class SupervisorMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.can_see_all_leads


class ApiKeyListView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'integrations/apikey_list.html'

    def get(self, request):
        keys = ApiKey.objects.all()
        logs = WebhookLog.objects.select_related('api_key', 'lead_creado').order_by('-created_at')[:50]
        return render(request, self.template_name, {'keys': keys, 'logs': logs})


class ApiKeyCreateView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'integrations/apikey_form.html'

    def get(self, request):
        from apps.users.models import User
        from apps.leads.models import Lead
        return render(request, self.template_name, {
            'agents': User.objects.filter(is_active=True),
            'estado_choices': Lead.ESTADO_CHOICES,
            'origen_choices': [('web','Web'),('campana','Campaña'),('referido','Referido'),('llamada','Llamada'),('whatsapp','WhatsApp')],
        })

    def post(self, request):
        from apps.users.models import User
        from apps.leads.models import Lead
        nombre = request.POST.get('nombre', '').strip()
        if not nombre:
            messages.error(request, 'El nombre es requerido.')
            return redirect('integrations:apikey_create')
        agente_id = request.POST.get('agente_default')
        key = ApiKey.objects.create(
            nombre=nombre,
            descripcion=request.POST.get('descripcion', '').strip(),
            origen_default=request.POST.get('origen_default', 'web'),
            agente_default=User.objects.filter(pk=agente_id).first() if agente_id else None,
            estado_inicial=request.POST.get('estado_inicial', 'nuevo'),
        )
        messages.success(request, f'API Key creada. Guardá esta clave: {key.key}')
        return redirect('integrations:list')


class ApiKeyToggleView(LoginRequiredMixin, SupervisorMixin, View):
    def post(self, request, pk):
        key = get_object_or_404(ApiKey, pk=pk)
        key.activa = not key.activa
        key.save(update_fields=['activa'])
        return JsonResponse({'activa': key.activa})


class ApiKeyDeleteView(LoginRequiredMixin, SupervisorMixin, View):
    def post(self, request, pk):
        key = get_object_or_404(ApiKey, pk=pk)
        key.delete()
        messages.success(request, 'API Key eliminada.')
        return redirect('integrations:list')


class ApiDocsView(LoginRequiredMixin, SupervisorMixin, View):
    template_name = 'integrations/api_docs.html'

    def get(self, request):
        from django.conf import settings
        base_url = request.build_absolute_uri('/').rstrip('/')
        return render(request, self.template_name, {'base_url': base_url})
