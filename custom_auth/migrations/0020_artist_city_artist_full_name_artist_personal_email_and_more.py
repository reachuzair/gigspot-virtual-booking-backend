# Generated by Django 5.1.8 on 2025-05-29 15:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom_auth', '0019_artist_stripe_account_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='artist',
            name='city',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='artist',
            name='full_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='artist',
            name='personal_email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='artist',
            name='phone_number',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
