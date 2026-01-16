from django.urls import path
from . import views

app_name = 'heirs'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('session/<uuid:link>/', views.session_lobby, name='session_lobby'),
    path('session/<uuid:link>/<int:heir_id>/', views.session_home, name='session_home'),
    path('session/<uuid:link>/<int:heir_id>/select/', views.select_assets, name='select_assets'),
]
