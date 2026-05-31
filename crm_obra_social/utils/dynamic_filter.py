"""
Dynamic multi-field filter builder.

URL format: ?q=texto&fc=campo&fo=operador&fv=valor&fc=campo2&fo=op2&fv=val2
fc/fo/fv are repeated GET params (getlist), zipped positionally.

Field types: text | choices | fk | number | date | extra_text | extra_bool | extra_lista | extra_fecha | extra_num
Fields from CampoPersonalizado use key prefix "extra__<slug>".
"""
from datetime import date, timedelta
from itertools import zip_longest

from django.db.models import Q, FloatField
from django.utils import timezone


# ─── Operator definitions ───────────────────────────────────────────────────

TEXT_OPS = [
    ('contains',     'contiene'),
    ('not_contains', 'no contiene'),
    ('eq',           'es igual a'),
    ('starts',       'empieza con'),
]
CHOICE_OPS = [('eq', 'es')]
FK_OPS     = [('eq', 'es')]
BOOL_OPS   = [('eq', 'es')]
NUMBER_OPS = [
    ('eq',  'igual a'),
    ('gte', 'mayor o igual a'),
    ('lte', 'menor o igual a'),
    ('gt',  'mayor que'),
    ('lt',  'menor que'),
]
DATE_OPS = [
    ('today',     'hoy'),
    ('yesterday', 'ayer'),
    ('this_week', 'esta semana'),
    ('this_month','este mes'),
    ('last_7',    'últimos 7 días'),
    ('last_30',   'últimos 30 días'),
    ('eq',        'en fecha exacta'),
    ('gte',       'desde'),
    ('lte',       'hasta'),
]
# For dates stored as ISO strings in datos_extra
DATE_STR_OPS = [
    ('eq',  'en fecha exacta'),
    ('gte', 'desde'),
    ('lte', 'hasta'),
]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _user_qs():
    from apps.users.models import User
    return list(User.objects.filter(is_active=True).values('pk', 'first_name', 'last_name', 'username'))


def _custom_field_def(campo):
    """Convert a CampoPersonalizado instance into a filter field definition."""
    from apps.leads.models import CampoPersonalizado as C
    key = f'extra__{campo.slug}'

    if campo.tipo == C.TIPO_TEXTO:
        return key, {'label': campo.nombre, 'type': 'extra_text', 'ops': TEXT_OPS, 'slug': campo.slug}
    if campo.tipo == C.TIPO_NUMERO:
        return key, {'label': campo.nombre, 'type': 'extra_num', 'ops': NUMBER_OPS, 'slug': campo.slug}
    if campo.tipo == C.TIPO_FECHA:
        return key, {'label': campo.nombre, 'type': 'extra_fecha', 'ops': DATE_STR_OPS, 'slug': campo.slug}
    if campo.tipo == C.TIPO_BOOLEANO:
        return key, {
            'label': campo.nombre, 'type': 'extra_bool', 'ops': BOOL_OPS, 'slug': campo.slug,
            'choices': [('true', 'Sí'), ('false', 'No')],
        }
    if campo.tipo == C.TIPO_LISTA:
        opts = [(o, o) for o in (campo.opciones or [])]
        return key, {'label': campo.nombre, 'type': 'extra_lista', 'ops': CHOICE_OPS, 'slug': campo.slug,
                     'choices': opts}
    return None, None


# ─── Field definitions ──────────────────────────────────────────────────────

def _lead_fields():
    from apps.leads.models import Lead, Plan, CampoPersonalizado
    fields = {
        'nombre_completo': {'label': 'Nombre',    'type': 'text', 'ops': TEXT_OPS},
        'dni':             {'label': 'DNI',       'type': 'text', 'ops': TEXT_OPS},
        'telefono':        {'label': 'Teléfono',  'type': 'text', 'ops': TEXT_OPS},
        'email':           {'label': 'Email',     'type': 'text', 'ops': TEXT_OPS},
        'localidad':       {'label': 'Localidad', 'type': 'text', 'ops': TEXT_OPS},
        'provincia':       {'label': 'Provincia', 'type': 'text', 'ops': TEXT_OPS},
        'estado':    {'label': 'Estado',    'type': 'choices', 'ops': CHOICE_OPS, 'choices': Lead.ESTADO_CHOICES},
        'prioridad': {'label': 'Prioridad', 'type': 'choices', 'ops': CHOICE_OPS, 'choices': Lead.PRIORIDAD_CHOICES},
        'origen':    {'label': 'Origen',    'type': 'choices', 'ops': CHOICE_OPS, 'choices': Lead.ORIGEN_CHOICES},
        'plan_interes': {'label': 'Plan', 'type': 'fk', 'ops': FK_OPS,
                         'queryset': lambda: list(Plan.objects.filter(activo=True).values('pk', 'nombre'))},
        'grupo_familiar': {'label': 'Grupo familiar', 'type': 'number', 'ops': NUMBER_OPS},
        'agente': {'label': 'Agente', 'type': 'fk', 'ops': FK_OPS, 'supervisor_only': True,
                   'queryset': _user_qs},
        'created_at': {'label': 'Fecha de creación',     'type': 'date', 'ops': DATE_OPS},
        'updated_at': {'label': 'Última actualización',  'type': 'date', 'ops': DATE_OPS},
    }
    # Append active custom fields for leads
    for campo in CampoPersonalizado.objects.filter(
        activo=True, alcance__in=['leads', 'ambos']
    ).order_by('orden', 'nombre'):
        key, fdef = _custom_field_def(campo)
        if key:
            fields[key] = fdef
    return fields


def _cliente_fields():
    from apps.leads.models import Plan, CampoPersonalizado
    fields = {
        'nombre_completo': {'label': 'Nombre',      'type': 'text', 'ops': TEXT_OPS},
        'dni':             {'label': 'DNI',         'type': 'text', 'ops': TEXT_OPS},
        'telefono':        {'label': 'Teléfono',    'type': 'text', 'ops': TEXT_OPS},
        'email':           {'label': 'Email',       'type': 'text', 'ops': TEXT_OPS},
        'localidad':       {'label': 'Localidad',   'type': 'text', 'ops': TEXT_OPS},
        'provincia':       {'label': 'Provincia',   'type': 'text', 'ops': TEXT_OPS},
        'plan': {'label': 'Plan', 'type': 'fk', 'ops': FK_OPS,
                 'queryset': lambda: list(Plan.objects.filter(activo=True).values('pk', 'nombre'))},
        'numero_afiliado': {'label': 'N° afiliado', 'type': 'text', 'ops': TEXT_OPS},
        'grupo_familiar':  {'label': 'Grupo familiar', 'type': 'number', 'ops': NUMBER_OPS},
        'agente': {'label': 'Agente', 'type': 'fk', 'ops': FK_OPS, 'supervisor_only': True,
                   'queryset': _user_qs},
        'created_at': {'label': 'Fecha de creación',    'type': 'date', 'ops': DATE_OPS},
        'updated_at': {'label': 'Última actualización', 'type': 'date', 'ops': DATE_OPS},
    }
    for campo in CampoPersonalizado.objects.filter(
        activo=True, alcance__in=['clientes', 'ambos']
    ).order_by('orden', 'nombre'):
        key, fdef = _custom_field_def(campo)
        if key:
            fields[key] = fdef
    return fields


# ─── Apply filters ───────────────────────────────────────────────────────────

def apply_dynamic_filters(qs, request, field_defs):
    """Apply fc/fo/fv filter params from GET to the queryset."""
    # zip_longest guards against misaligned lists (e.g. missing fv for no-value date ops)
    for field_name, op, val in zip_longest(
        request.GET.getlist('fc'),
        request.GET.getlist('fo'),
        request.GET.getlist('fv'),
        fillvalue='',
    ):
        field_name = (field_name or '').strip()
        op         = (op or '').strip()
        val        = (val or '').strip()
        if not field_name or field_name not in field_defs:
            continue
        fdef = field_defs[field_name]
        if fdef.get('supervisor_only') and not request.user.can_see_all_leads:
            continue

        try:
            ftype = fdef['type']
            if ftype == 'text':
                qs = _apply_text(qs, field_name, op, val)
            elif ftype == 'choices':
                if val:
                    qs = qs.filter(**{field_name: val})
            elif ftype == 'fk':
                if val:
                    # Use _id suffix for FK fields to avoid ORM ambiguity
                    qs = qs.filter(**{f'{field_name}_id': val})
            elif ftype == 'number':
                qs = _apply_number(qs, field_name, op, val)
            elif ftype == 'date':
                qs = _apply_date(qs, field_name, op, val)
            # ── Custom fields (datos_extra) ──
            elif ftype == 'extra_text':
                slug = fdef['slug']
                qs = _apply_text(qs, f'datos_extra__{slug}', op, val)
            elif ftype == 'extra_num':
                qs = _apply_extra_number(qs, fdef['slug'], op, val)
            elif ftype == 'extra_fecha':
                qs = _apply_extra_date_str(qs, fdef['slug'], op, val)
            elif ftype == 'extra_bool':
                if val in ('true', 'false'):
                    qs = qs.filter(**{f'datos_extra__{fdef["slug"]}': val == 'true'})
            elif ftype == 'extra_lista':
                if val:
                    qs = qs.filter(**{f'datos_extra__{fdef["slug"]}': val})
        except (ValueError, TypeError):
            pass

    return qs


# ─── Per-type apply helpers ──────────────────────────────────────────────────

def _apply_text(qs, field, op, val):
    if not val:
        return qs
    if op == 'contains':
        return qs.filter(**{f'{field}__icontains': val})
    if op == 'not_contains':
        return qs.exclude(**{f'{field}__icontains': val})
    if op == 'eq':
        return qs.filter(**{f'{field}__iexact': val})
    if op == 'starts':
        return qs.filter(**{f'{field}__istartswith': val})
    return qs


def _apply_number(qs, field, op, val):
    if not val:
        return qs
    n = float(val)
    suffix = {'eq': '', 'gt': '__gt', 'lt': '__lt', 'gte': '__gte', 'lte': '__lte'}.get(op, '')
    return qs.filter(**{f'{field}{suffix}': n})


def _apply_date(qs, field, op, val):
    today = timezone.now().date()
    if op == 'today':
        return qs.filter(**{f'{field}__date': today})
    if op == 'yesterday':
        return qs.filter(**{f'{field}__date': today - timedelta(days=1)})
    if op == 'this_week':
        start = today - timedelta(days=today.weekday())
        return qs.filter(**{f'{field}__date__gte': start, f'{field}__date__lte': today})
    if op == 'this_month':
        return qs.filter(**{f'{field}__year': today.year, f'{field}__month': today.month})
    if op == 'last_7':
        return qs.filter(**{f'{field}__date__gte': today - timedelta(days=7)})
    if op == 'last_30':
        return qs.filter(**{f'{field}__date__gte': today - timedelta(days=30)})
    if not val:
        return qs
    d = date.fromisoformat(val)
    if op == 'eq':
        return qs.filter(**{f'{field}__date': d})
    if op == 'gte':
        return qs.filter(**{f'{field}__date__gte': d})
    if op == 'lte':
        return qs.filter(**{f'{field}__date__lte': d})
    return qs


def _apply_extra_number(qs, slug, op, val):
    """Filter on a custom number field stored as string in datos_extra."""
    if not val:
        return qs
    try:
        from django.db.models.functions import Cast
        from django.db.models.expressions import KeyTextTransform
        n = float(val)
        ann_key = f'_extra_num_{slug}'
        qs = qs.annotate(**{
            ann_key: Cast(KeyTextTransform(slug, 'datos_extra'), output_field=FloatField())
        })
        suffix = {'eq': '', 'gt': '__gt', 'lt': '__lt', 'gte': '__gte', 'lte': '__lte'}.get(op, '')
        return qs.filter(**{f'{ann_key}{suffix}': n})
    except Exception:
        # Fallback: string contains for exact
        return qs.filter(**{f'datos_extra__{slug}__icontains': val})


def _apply_extra_date_str(qs, slug, op, val):
    """Filter on a date stored as ISO string in datos_extra."""
    if not val:
        return qs
    # ISO dates stored as strings: lexicographic comparison works correctly
    if op == 'eq':
        return qs.filter(**{f'datos_extra__{slug}': val})
    if op == 'gte':
        return qs.filter(**{f'datos_extra__{slug}__gte': val})
    if op == 'lte':
        return qs.filter(**{f'datos_extra__{slug}__lte': val})
    return qs


# ─── Build JS-friendly field config ─────────────────────────────────────────

def fields_for_js(field_defs, user):
    """Return a JSON-serializable dict describing all available filter fields."""
    result = {}
    for key, fdef in field_defs.items():
        if fdef.get('supervisor_only') and not user.can_see_all_leads:
            continue
        ftype = fdef['type']
        entry = {
            'label': fdef['label'],
            'type':  ftype,
            'ops':   fdef['ops'],
        }
        # Fields that need an options list in the JS
        if ftype in ('choices', 'extra_bool', 'extra_lista'):
            entry['options'] = [{'v': v, 'l': l} for v, l in fdef['choices']]
        elif ftype == 'fk':
            raw = fdef['queryset']()
            entry['options'] = [
                {'v': str(r['pk']),
                 'l': r.get('nombre') or
                      f"{r.get('first_name','')} {r.get('last_name','')}".strip() or
                      r.get('username', '')}
                for r in raw
            ]
        result[key] = entry
    return result
