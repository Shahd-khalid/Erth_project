from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='index'), # Changed name to index to avoid conflict if needed, but 'dashboard' is fine if namespaced. 
    # Actually, the project urls include it as 'dashboard/', so this is 'dashboard:index' or just 'dashboard' if no app_name.
    # Let's keep it simple.
]
