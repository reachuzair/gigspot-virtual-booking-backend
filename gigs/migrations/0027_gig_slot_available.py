# Generated by Django 5.1.7 on 2025-05-14 15:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gigs', '0026_gig_collaborators'),
    ]

    operations = [
        migrations.AddField(
            model_name='gig',
            name='slot_available',
            field=models.BooleanField(default=True),
        ),
    ]
