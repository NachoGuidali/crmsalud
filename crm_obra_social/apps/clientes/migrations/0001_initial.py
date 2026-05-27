import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('leads', '0004_campopersonalizado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Cliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre_completo', models.CharField(max_length=200, verbose_name='Nombre completo')),
                ('dni', models.CharField(blank=True, max_length=20, verbose_name='DNI')),
                ('fecha_nacimiento', models.DateField(blank=True, null=True, verbose_name='Fecha de nacimiento')),
                ('telefono', models.CharField(blank=True, max_length=30, verbose_name='Teléfono')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email')),
                ('localidad', models.CharField(blank=True, max_length=100, verbose_name='Localidad')),
                ('provincia', models.CharField(blank=True, max_length=100, verbose_name='Provincia')),
                ('numero_afiliado', models.CharField(blank=True, max_length=50, verbose_name='N° de afiliado')),
                ('grupo_familiar', models.PositiveSmallIntegerField(default=1, verbose_name='Grupo familiar')),
                ('notas', models.TextField(blank=True, verbose_name='Notas')),
                ('datos_extra', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('agente', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='clientes_asignados',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Agente',
                )),
                ('plan', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='leads.plan',
                    verbose_name='Plan',
                )),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'ordering': ['-created_at'],
            },
        ),
    ]
