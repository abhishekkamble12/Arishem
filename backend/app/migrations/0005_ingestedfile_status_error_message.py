# Generated manually

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_driftlog_predictionlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='ingestedfile',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('PROCESSING', 'Processing'),
                    ('SUCCESS', 'Success'),
                    ('FAILED', 'Failed')
                ],
                default='SUCCESS',
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='error_message',
            field=models.TextField(blank=True, null=True),
        ),
    ]
