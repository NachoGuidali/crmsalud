import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0005_lead_motivo_perdida'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Documento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200, verbose_name='Descripción')),
                ('tipo', models.CharField(
                    choices=[
                        ('recibo_sueldo', 'Recibo de sueldo'),
                        ('dni', 'DNI'),
                        ('contrato', 'Contrato / formulario'),
                        ('otro', 'Otro'),
                    ],
                    default='otro', max_length=30, verbose_name='Tipo',
                )),
                ('archivo', models.FileField(upload_to='documentos/%Y/%m/', verbose_name='Archivo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('lead', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos',
                    to='leads.lead',
                )),
                ('subido_por', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='documentos_subidos',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Documento',
                'verbose_name_plural': 'Documentos',
                'ordering': ['-created_at'],
            },
        ),
    ]
