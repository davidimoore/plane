# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0116_workspacemember_explored_features_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='exporterhistory',
            name='progress_percentage',
            field=models.IntegerField(default=0, help_text='Export progress as a percentage (0-100)'),
        ),
        migrations.AddField(
            model_name='exporterhistory',
            name='total_items',
            field=models.IntegerField(default=0, help_text='Total number of items to export'),
        ),
        migrations.AddField(
            model_name='exporterhistory',
            name='processed_items',
            field=models.IntegerField(default=0, help_text='Number of items processed so far'),
        ),
    ]
