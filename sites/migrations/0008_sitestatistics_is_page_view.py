# Generated by Django 5.1 on 2024-08-27 11:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0007_sitestatistics_css_count_sitestatistics_css_size_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitestatistics',
            name='is_page_view',
            field=models.BooleanField(default=False),
        ),
    ]
