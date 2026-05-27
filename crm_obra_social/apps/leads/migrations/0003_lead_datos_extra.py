from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='datos_extra',
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name='Datos extra',
                help_text='Columnas adicionales importadas desde CSV/Excel.',
            ),
        ),
    ]
