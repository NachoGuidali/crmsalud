from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0008_mensaje_media_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversacion',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pendiente', 'Pendiente'),
                    ('abierta', 'Abierta'),
                    ('cerrada', 'Cerrada'),
                ],
                db_index=True,
                default='pendiente',
                max_length=20,
                verbose_name='Estado',
            ),
        ),
    ]
