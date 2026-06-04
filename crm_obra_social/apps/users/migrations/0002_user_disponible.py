from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='disponible',
            field=models.BooleanField(
                default=True,
                verbose_name='Disponible para asignaciones',
                help_text='Desactivar en vacaciones o ausencia. Sus conversaciones se redistribuyen automáticamente.',
            ),
        ),
    ]
