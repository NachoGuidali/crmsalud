"""
Dynamic multi-field filter builder.

URL format: ?q=texto&fc=campo&fo=operador&fv=valor&fc=campo2&fo=op2&fv=val2
fc/fo/fv are repeated GET params (getlist), zipped positionally.

Field types: text | choices | fk | number | date
"""
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone


# ─── Operator definitions ───────────────────────────────────────────────────

TEXT_OPS = [
    ('contains',     'contiene'),
    ('not_contains', 'no contiene'),
    ('eq',           'es igual a'),
    ('starts',       'empieza con'),
]
CHOICE_OPS  = [('eq', 'es')]
FK_OPS      = [('eq', 'es')]
NUMBER_OPS  = [
    ('eq',  'igual a'),
    ('gte', 'mayor o igual a'),
    ('lte', 'menor o igual a'),
    ('gt',  'mayor que'),
    ('lt',  'menor que'),
]
DATE_OPS = [
    ('today',      'hoy'),
    ('yesterday',  'ayer'),
    ('this_week',  'esta semana'),
    ('this_month', 'este mes'),
    ('last_7',     'últimos 7 días'),
    ('last_30',    'últimos 30 días'),
    ('eq',         'en fecha exacta'),
    ('gte',        'desde'),
    ('lte',        'hasta'),
]


# ─── Field definitions ──────────────────────────────────────────────────────

def _user_qs():
    from apps.users.models import User
    return list(User.objects.filter(is_active=True).values('pk', 'first_name', 'last_name', 'username'))

def _lead_fields():
    from apps.leads.models import Lead, Plan
    from apps.users.models import User
    return {
        'nombre_completo': {'label': 'Nombre', 'type': 'text', 'ops': TEXT_OPS},
        'dni':             {'label': 'DNI',    'type': 'text', 'ops': TEXT_OPS},
        'telefono':        {'label': 'Teléfono', 'type': 'text', 'ops': TEXT_OPS},
        'email':           {'label': 'Email',  'type': 'text', 'ops': TEXT_OPS},
        'localidad':       {'label': 'Localidad', 'type': 'text', 'ops': TEXT_OPS},
        'provincia':       {'label': 'Provincia', 'type': 'text', 'ops': TEXT_OPS},
        'estado':          {'label': 'Estado', 'type': 'choices', 'ops': CHOICE_OPS,
                            'choices': Lead.ESTADO_CHOICES},
        'prioridad':       {'label': 'Prioridad', 'type': 'choices', 'ops': CHOICE_OPS,
                            'choices': Lead.PRIORIDAD_CHOICES},
        'origen':          {'label': 'Origen', 'type': 'choices', 'ops': CHOICE_OPS,
                            'choices': Lead.ORIGEN_CHOICES},
        'plan_interes':    {'label': 'Plan', 'type': 'fk', 'ops': FK_OPS,
                            'queryset': lambda: list(Plan.objects.filter(activo=True).values('pk', 'nombre'))},
        'grupo_familiar':  {'label': 'Grupo familiar', 'type': 'number', 'ops': NUMBER_OPS},
        'agente':          {'label': 'Agente', 'type': 'fk', 'ops': FK_OPS, 'supervisor_only': True,
                            'queryset': _user_qs},
        'created_at':      {'label': 'Fecha de creación', 'type': 'date', 'ops': DATE_OPS},
        'updated_at':      {'label': 'Última actualización', 'type': 'date', 'ops': DATE_OPS},
    }


def _cliente_fields():
    from apps.leads.models import Plan
    return {
        'nombre_completo': {'label': 'Nombre',   'type': 'text', 'ops': TEXT_OPS},
        'dni':             {'label': 'DNI',      'type': 'text', 'ops': TEXT_OPS},
        'telefono':        {'label': 'Teléfono', 'type': 'text', 'ops': TEXT_OPS},
        'email':           {'label': 'Email',    'type': 'text', 'ops': TEXT_OPS},
        'localidad':       {'label': 'Localidad', 'type': 'text', 'ops': TEXT_OPS},
        'provincia':       {'label': 'Provincia', 'type': 'text', 'ops': TEXT_OPS},
        'plan':            {'label': 'Plan', 'type': 'fk', 'ops': FK_OPS,
                            'queryset': lambda: list(Plan.objects.filter(activo=True).values('pk', 'nombre'))},
        'numero_afiliado': {'label': 'N° afiliado', 'type': 'text', 'ops': TEXT_OPS},
        'grupo_familiar':  {'label': 'Grupo familiar', 'type': 'number', 'ops': NUMBER_OPS},
        'agente':          {'label': 'Agente', 'type': 'fk', 'ops': FK_OPS, 'supervisor_only': True,
                            'queryset': _user_qs},
        'created_at':      {'label': 'Fecha de creación', 'type': 'date', 'ops': DATE_OPS},
        'updated_at':      {'label': 'Última actualización', 'type': 'date', 'ops': DATE_OPS},
    }


# ─── Apply filters ───────────────────────────────────────────────────────────

def apply_dynamic_filters(qs, request, field_defs):
    """Apply fc/fo/fv filter params from GET to the queryset."""
    fields_raw = request.GET.getlist('fc')
    ops_raw    = request.GET.getlist('fo')
    vals_raw   = request.GET.getlist('fv')

    for field_name, op, val in zip(fields_raw, ops_raw, vals_raw):
        field_name = field_name.strip()
        val        = val.strip()
        if field_name not in field_defs:
            continue

        fdef = field_defs[field_name]
        if fdef.get('supervisor_only') and not request.user.can_see_all_leads:
            continue

        ftype = fdef['type']

        try:
            if ftype == 'text':
                qs = _apply_text(qs, field_name, op, val)
            elif ftype in ('choices', 'fk'):
                if val:
                    qs = qs.filter(**{field_name: val})
            elif ftype == 'number':
                qs = _apply_number(qs, field_name, op, val)
            elif ftype == 'date':
                qs = _apply_date(qs, field_name, op, val)
        except (ValueError, TypeError):
            pass

    return qs


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
    mapping = {'eq': '', 'gt': '__gt', 'lt': '__lt', 'gte': '__gte', 'lte': '__lte'}
    suffix = mapping.get(op, '')
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

    # Exact date / gte / lte need a value
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


# ─── Build JS-friendly field config ─────────────────────────────────────────

def fields_for_js(field_defs, user):
    """Return a JSON-serializable dict describing all available filter fields."""
    import json
    result = {}
    for key, fdef in field_defs.items():
        if fdef.get('supervisor_only') and not user.can_see_all_leads:
            continue
        entry = {
            'label': fdef['label'],
            'type':  fdef['type'],
            'ops':   fdef['ops'],
        }
        if fdef['type'] in ('choices', 'fk'):
            if fdef['type'] == 'choices':
                entry['options'] = [{'v': v, 'l': l} for v, l in fdef['choices']]
            else:
                raw = fdef['queryset']()
                entry['options'] = [
                    {'v': str(r['pk']),
                     'l': r.get('nombre') or f"{r.get('first_name','')} {r.get('last_name','')}".strip() or r.get('username','')}
                    for r in raw
                ]
        result[key] = entry
    return result
