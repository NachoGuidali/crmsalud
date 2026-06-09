from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_disponible'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ultimo_ping_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Último ping de actividad'),
        ),
        migrations.AlterField(
            model_name='user',
            name='disponible',
            field=models.BooleanField(
                default=True,
                help_text='Se activa al iniciar sesión y se desactiva al cerrar o por inactividad. Solo agentes en turno reciben conversaciones nuevas.',
                verbose_name='En turno',
            ),
        ),
    ]
