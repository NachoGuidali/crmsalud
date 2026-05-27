from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0004_campopersonalizado'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='motivo_perdida',
            field=models.TextField(
                blank=True,
                verbose_name='Motivo de pérdida',
                help_text='Completar cuando el lead se marca como "Perdido / No interesado".',
            ),
        ),
    ]
