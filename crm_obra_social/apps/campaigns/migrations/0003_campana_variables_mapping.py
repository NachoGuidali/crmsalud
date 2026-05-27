from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='campana',
            name='variables_mapping',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='Mapeo de variables',
                help_text='Define cómo se rellenan {{1}}, {{2}}... de la plantilla para cada lead.',
            ),
        ),
    ]
