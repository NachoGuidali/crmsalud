from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0007_conversacion_bot_toggles'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensaje',
            name='media_mime',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='mensaje',
            name='media_filename',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='mensaje',
            name='media_url',
            field=models.URLField(blank=True, max_length=2000),
        ),
    ]
