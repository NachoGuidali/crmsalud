import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0002_whatsapp_extras'),
    ]

    operations = [
        migrations.CreateModel(
            name='BotRespuesta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, verbose_name='Nombre de la regla')),
                ('activa', models.BooleanField(db_index=True, default=True)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('trigger_tipo', models.CharField(choices=[('primer_mensaje', 'Primer mensaje del contacto (bienvenida)'), ('palabra_clave', 'Contiene palabras clave')], max_length=20, verbose_name='Disparador')),
                ('palabras_clave', models.JSONField(blank=True, default=list, verbose_name='Palabras clave')),
                ('respuesta_tipo', models.CharField(choices=[('texto', 'Texto libre'), ('plantilla', 'Plantilla HSM'), ('interactivo', 'Mensaje con botones')], default='texto', max_length=20)),
                ('respuesta_texto', models.TextField(blank=True, verbose_name='Texto de respuesta')),
                ('respuesta_plantilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bot_reglas', to='whatsapp.plantillahsm', verbose_name='Plantilla HSM')),
                ('respuesta_interactivo_body', models.TextField(blank=True, verbose_name='Cuerpo del mensaje interactivo')),
                ('respuesta_interactivo_botones', models.JSONField(blank=True, default=list, verbose_name='Botones')),
                ('accion_estado', models.CharField(blank=True, max_length=20, verbose_name='Cambiar estado del lead a')),
                ('accion_prioridad', models.CharField(blank=True, max_length=10, verbose_name='Cambiar prioridad del lead a')),
                ('solo_si_sin_agente', models.BooleanField(default=False, verbose_name='Solo si no tiene agente asignado')),
                ('solo_primera_vez', models.BooleanField(default=True, verbose_name='Solo responder una vez por conversación')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'Regla de bot', 'verbose_name_plural': 'Reglas de bot WhatsApp', 'ordering': ['orden', 'nombre']},
        ),
        migrations.CreateModel(
            name='LogBotRespuesta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('respondido_at', models.DateTimeField(auto_now_add=True)),
                ('conversacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bot_logs', to='whatsapp.conversacion')),
                ('regla', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='whatsapp.botrespuesta')),
            ],
            options={'unique_together': {('conversacion', 'regla')}},
        ),
    ]
