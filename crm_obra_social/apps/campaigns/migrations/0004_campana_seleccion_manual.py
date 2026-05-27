from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0003_campana_variables_mapping'),
    ]

    operations = [
        migrations.AddField(
            model_name='campana',
            name='modo_seleccion',
            field=models.CharField(
                choices=[('segmento', 'Por segmento (filtros automáticos)'), ('manual', 'Selección manual de contactos')],
                default='segmento',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='campana',
            name='contactos_ids',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de IDs de leads seleccionados manualmente.',
                verbose_name='Contactos seleccionados',
            ),
        ),
    ]
