# Generated by Django 3.0.4 on 2020-03-23 10:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('debt_manager_backend_api', '0004_currency_current'),
    ]

    operations = [
        migrations.RenameField(
            model_name='transaction',
            old_name='data',
            new_name='date',
        ),
    ]
