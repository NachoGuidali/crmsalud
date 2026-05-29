from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0006_evolution_api_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversacion',
            name='bot_crm_activo',
            field=models.BooleanField(default=True, verbose_name='Bot CRM activo'),
        ),
        migrations.AddField(
            model_name='conversacion',
            name='bot_n8n_activo',
            field=models.BooleanField(default=True, verbose_name='Bot n8n activo'),
        ),
    ]
