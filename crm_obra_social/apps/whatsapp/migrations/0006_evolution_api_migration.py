from django.db import migrations, models


def set_plantillas_activas(apps, schema_editor):
    PlantillaHSM = apps.get_model('whatsapp', 'PlantillaHSM')
    PlantillaHSM.objects.all().update(activa=True)


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0005_configuracionwhatsapp'),
    ]

    operations = [
        # ConfiguracionWhatsApp: remove Meta fields, add Evolution API fields
        migrations.RemoveField(model_name='configuracionwhatsapp', name='access_token'),
        migrations.RemoveField(model_name='configuracionwhatsapp', name='phone_number_id'),
        migrations.RemoveField(model_name='configuracionwhatsapp', name='business_account_id'),
        migrations.RemoveField(model_name='configuracionwhatsapp', name='app_secret'),
        migrations.RemoveField(model_name='configuracionwhatsapp', name='webhook_verify_token'),
        migrations.AddField(
            model_name='configuracionwhatsapp',
            name='evolution_api_url',
            field=models.CharField(blank=True, max_length=200, verbose_name='Evolution API URL'),
        ),
        migrations.AddField(
            model_name='configuracionwhatsapp',
            name='evolution_api_key',
            field=models.CharField(blank=True, max_length=200, verbose_name='API Key'),
        ),
        migrations.AddField(
            model_name='configuracionwhatsapp',
            name='evolution_instance_name',
            field=models.CharField(blank=True, default='crm-supreg', max_length=100, verbose_name='Nombre de instancia'),
        ),
        migrations.AddField(
            model_name='configuracionwhatsapp',
            name='webhook_token',
            field=models.CharField(blank=True, max_length=100, verbose_name='Token de webhook', help_text='Token secreto que Evolution API envía en el header al hacer webhook'),
        ),
        # Conversacion: remove 24h window fields
        migrations.RemoveField(model_name='conversacion', name='ventana_activa'),
        migrations.RemoveField(model_name='conversacion', name='ventana_expira_at'),
        # PlantillaHSM: remove Meta-specific fields
        migrations.RemoveField(model_name='plantillahsm', name='nombre_meta'),
        migrations.RemoveField(model_name='plantillahsm', name='meta_template_id'),
        migrations.RemoveField(model_name='plantillahsm', name='ultimo_sync_at'),
        migrations.RemoveField(model_name='plantillahsm', name='status'),
        migrations.RemoveField(model_name='plantillahsm', name='categoria'),
        migrations.AlterModelOptions(
            name='plantillahsm',
            options={'ordering': ['nombre'], 'verbose_name': 'Plantilla de Mensaje', 'verbose_name_plural': 'Plantillas de Mensaje'},
        ),
        # Ensure all existing templates are active
        migrations.RunPython(set_plantillas_activas, migrations.RunPython.noop),
    ]
