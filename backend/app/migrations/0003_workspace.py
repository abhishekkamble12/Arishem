from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0002_alter_user_groups_alter_user_is_active'),
    ]

    operations = [
        migrations.CreateModel(
            name='Workspace',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('members', models.ManyToManyField(related_name='workspaces', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='workspace',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='files',
                to='app.workspace',
            ),
        ),
    ]
