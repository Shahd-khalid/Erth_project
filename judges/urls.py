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
    path('case/<int:case_id>/allocate/obligations/', views.allocate_obligations, name='allocate_obligations'),
    path('case/<int:case_id>/allocate/heirs/', views.allocate_heirs, name='allocate_heirs'),
    path('case/<int:case_id>/finalize/', views.finalize_case_distribution_request, name='finalize_case_distribution'),
    path('case/<int:case_id>/approve_mutual/', views.approve_mutual_consent, name='approve_mutual_consent'),
    path('case/raffle/<int:dispute_id>/resolve/', views.resolve_raffle, name='resolve_raffle'),
    path('case/settlement/<int:settlement_id>/confirm/', views.confirm_payment, name='confirm_payment'),
    path('export/print/', views.report_print_view, name='report_print'),
]
