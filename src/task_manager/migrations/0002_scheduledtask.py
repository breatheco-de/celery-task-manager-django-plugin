# Generated by Django 5.0.2 on 2024-03-23 07:13

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('task_manager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduledTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_module', models.CharField(max_length=200)),
                ('task_name', models.CharField(max_length=200)),
                ('arguments', models.JSONField(blank=True, default=dict, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('DONE', 'Done'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=20)),
                ('eta', models.DateTimeField(help_text='Estimated time of arrival')),
                ('duration', models.DurationField(default=datetime.timedelta, help_text='Duration of the session')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
