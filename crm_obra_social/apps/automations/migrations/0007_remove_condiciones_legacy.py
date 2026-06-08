from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('automations', '0006_migrar_datos_legacy'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reglaautomatizacion',
            name='condicion_estado',
        ),
        migrations.RemoveField(
            model_name='reglaautomatizacion',
            name='condicion_origen',
        ),
        migrations.RemoveField(
            model_name='reglaautomatizacion',
            name='condicion_prioridad',
        ),
    ]
