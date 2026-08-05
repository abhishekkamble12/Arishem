from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_ingestedfile_status_error_message'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='ingestedfile',
            unique_together=set(),
        ),
        migrations.RenameField(
            model_name='ingestedfile',
            old_name='s3_bucket',
            new_name='object_bucket',
        ),
        migrations.RenameField(
            model_name='ingestedfile',
            old_name='s3_key',
            new_name='object_key',
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='detected_topics',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='document_category',
            field=models.CharField(choices=[('policy', 'Policy'), ('sop', 'SOP'), ('contract', 'Contract'), ('audit', 'Audit'), ('hr', 'HR'), ('legal', 'Legal'), ('training', 'Training'), ('meeting', 'Meeting'), ('finance', 'Finance'), ('other', 'Other')], default='other', max_length=20),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='last_indexed_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='original_filename',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='summary',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ingestedfile',
            name='title',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='ingestedfile',
            unique_together={('object_bucket', 'object_key')},
        ),
    ]
