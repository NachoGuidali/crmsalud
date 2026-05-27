import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('leads', '0003_lead_datos_extra'),
        ('whatsapp', '0002_whatsapp_extras'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReglaAutomatizacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200, verbose_name='Nombre de la regla')),
                ('descripcion', models.TextField(blank=True, verbose_name='Descripción')),
                ('activa', models.BooleanField(db_index=True, default=True, verbose_name='Activa')),
                ('orden', models.PositiveSmallIntegerField(default=0, verbose_name='Orden de ejecución')),
                ('trigger_tipo', models.CharField(choices=[('tiempo_desde_creacion', 'N días desde que ingresó el lead'), ('tiempo_sin_cambio', 'N días sin actividad en el lead'), ('tiempo_sin_respuesta_wa', 'N días sin respuesta de WhatsApp del cliente')], max_length=30, verbose_name='Disparador')),
                ('trigger_dias', models.PositiveSmallIntegerField(verbose_name='Días')),
                ('condicion_estado', models.CharField(blank=True, max_length=20, verbose_name='Solo si estado es')),
                ('condicion_prioridad', models.CharField(blank=True, max_length=10, verbose_name='Solo si prioridad es')),
                ('condicion_origen', models.CharField(blank=True, max_length=20, verbose_name='Solo si origen es')),
                ('accion_tipo', models.CharField(choices=[('cambiar_estado', 'Cambiar estado del lead'), ('cambiar_prioridad', 'Cambiar prioridad del lead'), ('enviar_plantilla_wa', 'Enviar plantilla de WhatsApp'), ('crear_tarea', 'Crear tarea para el agente asignado')], max_length=30, verbose_name='Acción')),
                ('accion_estado_destino', models.CharField(blank=True, max_length=20, verbose_name='Estado destino')),
                ('accion_prioridad_destino', models.CharField(blank=True, max_length=10, verbose_name='Prioridad destino')),
                ('accion_plantilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='whatsapp.plantillahsm', verbose_name='Plantilla HSM')),
                ('accion_tarea_descripcion', models.TextField(blank=True, verbose_name='Descripción de la tarea')),
                ('accion_tarea_dias_plazo', models.PositiveSmallIntegerField(default=1, verbose_name='Plazo de la tarea (días)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Regla de automatización', 'verbose_name_plural': 'Reglas de automatización', 'ordering': ['orden', 'nombre']},
        ),
        migrations.CreateModel(
            name='AutomatizacionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ejecutado_at', models.DateTimeField(auto_now_add=True)),
                ('resultado', models.TextField(blank=True)),
                ('exitoso', models.BooleanField(default=True)),
                ('regla', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='automations.reglaautomatizacion')),
                ('lead', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='automatizacion_logs', to='leads.lead')),
            ],
            options={'verbose_name': 'Log de automatización', 'verbose_name_plural': 'Logs de automatización', 'ordering': ['-ejecutado_at']},
        ),
        migrations.AddConstraint(
            model_name='automatizacionlog',
            constraint=models.UniqueConstraint(fields=['regla', 'lead'], name='unique_regla_lead'),
        ),
    ]
