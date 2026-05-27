import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('leads', '0003_lead_datos_extra'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200, verbose_name='Nombre / origen')),
                ('descripcion', models.TextField(blank=True, verbose_name='Descripción')),
                ('key', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('activa', models.BooleanField(db_index=True, default=True)),
                ('origen_default', models.CharField(choices=[('web', 'Web'), ('campana', 'Campaña'), ('referido', 'Referido'), ('llamada', 'Llamada entrante'), ('whatsapp', 'WhatsApp')], default='web', max_length=20, verbose_name='Origen por defecto')),
                ('agente_default', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Agente asignado por defecto')),
                ('estado_inicial', models.CharField(default='nuevo', max_length=20, verbose_name='Estado inicial del lead')),
                ('ultimo_uso_at', models.DateTimeField(blank=True, null=True, verbose_name='Último uso')),
                ('total_usos', models.PositiveIntegerField(default=0, verbose_name='Total de usos')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name': 'API Key', 'verbose_name_plural': 'API Keys', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='WebhookLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.CharField(max_length=200)),
                ('method', models.CharField(max_length=10)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('request_body', models.TextField(blank=True)),
                ('response_status', models.PositiveSmallIntegerField(default=200)),
                ('response_body', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('ok', 'OK'), ('error', 'Error')], default='ok', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='logs', to='integrations.apikey')),
                ('lead_creado', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_logs', to='leads.lead')),
            ],
            options={'verbose_name': 'Log de webhook', 'verbose_name_plural': 'Logs de webhook', 'ordering': ['-created_at']},
        ),
    ]
