from django.urls import path
from . import views

app_name = 'cases'

urlpatterns = [
    path('', views.case_list, name='case_list'),
    path('create/', views.create_case, name='create_case'),
    path('<int:case_id>/review/', views.review_distribution, name='review_distribution'),
    path('<int:case_id>/review/<str:section>/', views.review_section, name='review_section'),
    path('<int:case_id>/lottery/', views.start_lottery, name='start_lottery'),
    path('<int:case_id>/lottery/run/', views.run_lottery, name='run_lottery'),
    path('<int:case_id>/report/', views.final_report, name='final_report'),
    path('<int:case_id>/allocate-share/<int:heir_id>/', views.allocate_share, name='allocate_share'),
    path('<int:case_id>/toggle-selection/', views.toggle_heir_selection, name='toggle_heir_selection'),
    path('<int:case_id>/timeline/', views.case_timeline, name='case_timeline'),
    path('<int:case_id>/call-window/', views.case_call_window, name='case_call_window'),
]
