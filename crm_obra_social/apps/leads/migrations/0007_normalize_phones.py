import re

from django.db import migrations


def _normalize(phone):
    if not phone:
        return phone
    cleaned = re.sub(r'[\s\-\(\).]', '', phone.strip())
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
    elif not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    if cleaned.startswith('+54'):
        after = cleaned[3:]
        if after and after[0] != '9':
            cleaned = '+549' + after
    return cleaned


def normalize_lead_phones(apps, schema_editor):
    Lead = apps.get_model('leads', 'Lead')
    for lead in Lead.objects.exclude(telefono='').iterator():
        normalized = _normalize(lead.telefono)
        if normalized != lead.telefono:
            Lead.objects.filter(pk=lead.pk).update(telefono=normalized)


def normalize_cliente_phones(apps, schema_editor):
    Cliente = apps.get_model('clientes', 'Cliente')
    for cliente in Cliente.objects.exclude(telefono='').iterator():
        normalized = _normalize(cliente.telefono)
        if normalized != cliente.telefono:
            Cliente.objects.filter(pk=cliente.pk).update(telefono=normalized)


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0006_documento'),
        ('clientes', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalize_lead_phones, migrations.RunPython.noop),
        migrations.RunPython(normalize_cliente_phones, migrations.RunPython.noop),
    ]
