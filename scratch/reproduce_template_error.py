import os
import django
from django.conf import settings
from django.template import Template, Context, loader

if not settings.configured:
    settings.configure(
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [r'c:\Users\PC\Desktop\mawareth_project\templates'],
        }],
        INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'],
    )
    django.setup()

try:
    t = loader.get_template('heirs/session_home.html')
    print("Success: Template compiled!")
except Exception as e:
    print(f"Error: {e}")
