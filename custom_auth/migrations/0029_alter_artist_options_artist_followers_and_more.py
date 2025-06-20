# Generated by Django 5.1.7 on 2025-06-05 20:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom_auth', '0028_initial_venue_tiers'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='artist',
            options={'ordering': ['-followers'], 'verbose_name': 'Artist', 'verbose_name_plural': 'Artists'},
        ),
        migrations.AddField(
            model_name='artist',
            name='followers',
            field=models.PositiveIntegerField(default=0, help_text='Number of followers on streaming platforms'),
        ),
        migrations.AddField(
            model_name='artist',
            name='last_metrics_update',
            field=models.DateTimeField(blank=True, help_text='When metrics were last updated', null=True),
        ),
        migrations.AddField(
            model_name='artist',
            name='monthly_listeners',
            field=models.PositiveIntegerField(default=0, help_text='Monthly listeners on streaming platforms'),
        ),
        migrations.AddField(
            model_name='artist',
            name='total_streams',
            field=models.PositiveBigIntegerField(default=0, help_text='Total streams across all platforms'),
        ),
        migrations.AlterField(
            model_name='artist',
            name='soundcharts_uuid',
            field=models.CharField(blank=True, default=None, max_length=255, null=True, unique=True),
        ),
    ]
