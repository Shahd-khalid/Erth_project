from django.urls import path
from . import views

app_name = 'judges'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('clerks/', views.clerk_list, name='manage_clerks'),
    path('clerks/<int:clerk_id>/select/', views.select_clerk, name='select_clerk'),
    path('case/<int:case_id>/accept/', views.accept_case, name='accept_case'),
    path('case/<int:case_id>/reject/', views.reject_case, name='reject_case'),
    path('case/<int:case_id>/assign_clerk/', views.assign_clerk, name='assign_clerk'),
    path('case/<int:case_id>/details/', views.case_details, name='case_details'),
    path('case/<int:case_id>/calculate/', views.perform_calculation, name='perform_calculation'),
    path('case/<int:case_id>/allocate/', views.allocate_assets, name='allocate_assets'),
]
