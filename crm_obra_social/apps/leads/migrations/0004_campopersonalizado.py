from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0003_lead_datos_extra'),
    ]

    operations = [
        migrations.CreateModel(
            name='CampoPersonalizado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('tipo', models.CharField(
                    choices=[('texto', 'Texto libre'), ('numero', 'Número'), ('fecha', 'Fecha'),
                             ('booleano', 'Sí / No'), ('lista', 'Lista de opciones')],
                    default='texto', max_length=20,
                )),
                ('alcance', models.CharField(
                    choices=[('leads', 'Solo Leads'), ('clientes', 'Solo Clientes'), ('ambos', 'Leads y Clientes')],
                    default='ambos', max_length=20,
                )),
                ('opciones', models.JSONField(blank=True, default=list)),
                ('requerido', models.BooleanField(default=False)),
                ('orden', models.PositiveIntegerField(default=0)),
                ('activo', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['orden', 'nombre'],
            },
        ),
        migrations.AddField(
            model_name='lead',
            name='motivo_perdida',
            field=models.TextField(
                blank=True,
                verbose_name='Motivo de pérdida',
                help_text='Completar cuando el lead se marca como "Perdido / No interesado".',
            ),
        ),
    ]
