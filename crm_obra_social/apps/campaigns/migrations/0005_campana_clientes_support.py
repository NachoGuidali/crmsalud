from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0004_campana_seleccion_manual'),
        ('clientes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='campana',
            name='tipo_destinatario',
            field=models.CharField(
                choices=[
                    ('leads', 'Solo Leads'),
                    ('clientes', 'Solo Clientes'),
                    ('todos', 'Leads y Clientes'),
                ],
                default='leads',
                max_length=10,
                verbose_name='Tipo de destinatarios',
            ),
        ),
        migrations.AddField(
            model_name='campana',
            name='contactos_clientes_ids',
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name='Clientes seleccionados',
            ),
        ),
        migrations.AddField(
            model_name='campanalog',
            name='cliente',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='clientes.cliente',
            ),
        ),
        migrations.AddField(
            model_name='campanalog',
            name='nombre_contacto',
            field=models.CharField(blank=True, default='', max_length=200),
            preserve_default=False,
        ),
    ]
