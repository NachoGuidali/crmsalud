from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0004_alter_plantillahsm_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionWhatsApp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.CharField(blank=True, max_length=500, verbose_name='Access Token')),
                ('phone_number_id', models.CharField(blank=True, max_length=50, verbose_name='Phone Number ID')),
                ('business_account_id', models.CharField(blank=True, max_length=50, verbose_name='Business Account ID')),
                ('app_secret', models.CharField(blank=True, max_length=200, verbose_name='App Secret')),
                ('webhook_verify_token', models.CharField(default='verify_token_default', max_length=100, verbose_name='Webhook Verify Token')),
            ],
            options={
                'verbose_name': 'Configuración WhatsApp',
                'verbose_name_plural': 'Configuración WhatsApp',
            },
        ),
    ]
