from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0009_alter_campopersonalizado_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='documento',
            name='url_externa',
            field=models.URLField(blank=True, max_length=2000, verbose_name='URL externa'),
        ),
        migrations.AddField(
            model_name='documento',
            name='fuente',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('whatsapp', 'WhatsApp')],
                default='manual',
                max_length=20,
                verbose_name='Fuente',
            ),
        ),
        migrations.AlterField(
            model_name='documento',
            name='archivo',
            field=models.FileField(blank=True, upload_to='documentos/%Y/%m/', verbose_name='Archivo'),
        ),
    ]
