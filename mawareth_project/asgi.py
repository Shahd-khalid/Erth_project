import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import cases.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            cases.routing.websocket_urlpatterns
        )
    ),
})
