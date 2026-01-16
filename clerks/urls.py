from django.urls import path
from . import views

app_name = 'clerks'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('accept_judge/', views.accept_judge, name='accept_judge'),
    path('reject_judge/', views.reject_judge, name='reject_judge'),
    path('case/<int:case_id>/enter_data/', views.enter_case_data, name='enter_case_data'),
]
