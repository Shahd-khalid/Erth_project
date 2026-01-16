from django.urls import path
from . import views

urlpatterns = [
    path('public/', views.public_calculator, name='public_calculator'),
]
