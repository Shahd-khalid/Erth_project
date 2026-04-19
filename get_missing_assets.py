import os
import django
try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import Asset

targets = [11, 12]
assets = Asset.objects.filter(id__in=targets)

for a in assets:
    # Print the description as unicode escape so I can decode Arabic characters
    desc_escaped = a.description.encode('unicode_escape').decode()
    print(f"ID:{a.id}|DESC:{desc_escaped}|IMG:{a.image.name}")
