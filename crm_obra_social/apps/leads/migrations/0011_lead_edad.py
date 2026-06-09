from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0010_documento_whatsapp'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='edad',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Edad'),
        ),
    ]
