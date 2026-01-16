import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from users.models import User

username = 'admin'
password = 'admin123'
email = 'admin@example.com'

if not User.objects.filter(username=username).exists():
    user = User.objects.create_superuser(username=username, email=email, password=password)
    user.role = User.Role.ADMIN
    user.save()
    print(f"Superuser '{username}' created successfully.")
else:
    u = User.objects.get(username=username)
    u.role = User.Role.ADMIN
    u.set_password(password)
    u.save()
    print(f"User '{username}' updated successfully.")
