from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0007_normalize_phones'),
    ]

    operations = [
        migrations.CreateModel(
            name='CampoRegla',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('condicion_tipo', models.CharField(
                    choices=[('siempre', 'Siempre'), ('estado', 'Cuando el estado del lead es')],
                    default='siempre', max_length=20,
                )),
                ('condicion_valor', models.CharField(
                    blank=True, max_length=50,
                    help_text='Valor del estado (ej: interesado)',
                )),
                ('accion', models.CharField(
                    choices=[
                        ('obligatorio', 'Obligatorio'),
                        ('visible', 'Visible'),
                        ('oculto', 'Oculto'),
                        ('solo_lectura', 'Solo lectura'),
                    ],
                    max_length=20,
                )),
                ('campo', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reglas',
                    to='leads.campopersonalizado',
                )),
            ],
            options={
                'verbose_name': 'Regla de campo',
                'verbose_name_plural': 'Reglas de campo',
                'ordering': ['campo', 'condicion_tipo'],
            },
        ),
    ]
