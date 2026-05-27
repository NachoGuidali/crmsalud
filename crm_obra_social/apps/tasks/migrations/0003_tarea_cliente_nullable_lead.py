import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0002_initial'),
        ('clientes', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tarea',
            name='lead',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tareas',
                to='leads.lead',
            ),
        ),
        migrations.AddField(
            model_name='tarea',
            name='cliente',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tareas',
                to='clientes.cliente',
            ),
        ),
    ]
