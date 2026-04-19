from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/session/(?P<session_link>[0-9a-f-]+)/$', consumers.CallConsumer.as_asgi()),
]
