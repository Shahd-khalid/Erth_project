from django.urls import path
from . import views

app_name = 'calculator'

urlpatterns = [
    path('public/', views.public_calculator, name='public_calculator'),
    path('public/results/', views.public_calculator_results, name='public_calculator_results'),
]
