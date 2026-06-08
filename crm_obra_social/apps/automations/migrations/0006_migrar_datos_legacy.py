from django.db import migrations


def migrar_datos(apps, schema_editor):
    ReglaAutomatizacion = apps.get_model('automations', 'ReglaAutomatizacion')
    CondicionRegla = apps.get_model('automations', 'CondicionRegla')

    # Mapea los trigger_tipo viejos a la nueva taxonomía (tipo_regla + trigger_tipo + campos extra)
    MAPA_TRIGGER = {
        'tiempo_desde_creacion': {
            'tipo_regla': 'automatizacion',
            'trigger_tipo': 'delay',
            'delay_unidad': 'dias',
        },
        'tiempo_sin_cambio': {
            'tipo_regla': 'automatizacion',
            'trigger_tipo': 'tiempo_sin_cambio',
        },
        'tiempo_sin_respuesta_wa': {
            'tipo_regla': 'automatizacion',
            'trigger_tipo': 'tiempo_sin_respuesta_wa',
        },
        'estado_cambio': {
            'tipo_regla': 'disparador',
            'trigger_tipo': 'campo_igual_a',
        },
    }

    for regla in ReglaAutomatizacion.objects.all():
        cambios = []

        mapa = MAPA_TRIGGER.get(regla.trigger_tipo)
        if mapa:
            for campo, valor in mapa.items():
                setattr(regla, campo, valor)
            if mapa.get('trigger_tipo') == 'delay':
                regla.delay_cantidad = regla.trigger_dias
            cambios.append('trigger')

        orden = 0
        join = 'AND'
        for campo_legacy, valor in (
            ('condicion_estado', regla.condicion_estado),
            ('condicion_prioridad', regla.condicion_prioridad),
            ('condicion_origen', regla.condicion_origen),
        ):
            if valor:
                campo_real = campo_legacy.replace('condicion_', '')
                CondicionRegla.objects.create(
                    regla=regla, orden=orden, campo=campo_real,
                    operador='eq', valor=valor, join_siguiente=join,
                )
                orden += 1

        if cambios:
            regla.save()


def revertir(apps, schema_editor):
    CondicionRegla = apps.get_model('automations', 'CondicionRegla')
    CondicionRegla.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('automations', '0005_condiciones_y_taxonomia_triggers'),
    ]

    operations = [
        migrations.RunPython(migrar_datos, revertir),
    ]
