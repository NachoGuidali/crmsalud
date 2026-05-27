from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0001_initial'),
    ]

    operations = [
        # PlantillaHSM — header, footer, buttons, Meta tracking
        migrations.AddField(
            model_name='plantillahsm',
            name='header_tipo',
            field=models.CharField(
                choices=[('none', 'Sin header'), ('text', 'Texto'), ('image', 'Imagen'), ('document', 'Documento'), ('video', 'Video')],
                default='none',
                max_length=10,
                verbose_name='Tipo de header',
            ),
        ),
        migrations.AddField(
            model_name='plantillahsm',
            name='header_contenido',
            field=models.TextField(
                blank=True,
                verbose_name='Contenido del header',
                help_text='Texto del header (si tipo=Texto) o URL del archivo',
            ),
        ),
        migrations.AddField(
            model_name='plantillahsm',
            name='footer',
            field=models.CharField(
                blank=True,
                max_length=60,
                verbose_name='Footer',
                help_text='Texto del pie de mensaje (máximo 60 caracteres)',
            ),
        ),
        migrations.AddField(
            model_name='plantillahsm',
            name='botones',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='Botones',
                help_text='[{"tipo":"reply","texto":"Sí"},{"tipo":"url","texto":"Ver","valor":"https://..."}]',
            ),
        ),
        migrations.AddField(
            model_name='plantillahsm',
            name='meta_template_id',
            field=models.CharField(blank=True, max_length=50, verbose_name='ID en Meta'),
        ),
        migrations.AddField(
            model_name='plantillahsm',
            name='ultimo_sync_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Último sync con Meta'),
        ),
        # Mensaje — ampliar max_length de media_url + agregar tipos video e interactive
        migrations.AlterField(
            model_name='mensaje',
            name='media_url',
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AlterField(
            model_name='mensaje',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('text', 'Texto'),
                    ('image', 'Imagen'),
                    ('document', 'Documento'),
                    ('audio', 'Audio'),
                    ('video', 'Video'),
                    ('template', 'Plantilla HSM'),
                    ('interactive', 'Interactivo'),
                ],
                default='text',
                max_length=20,
            ),
        ),
    ]
