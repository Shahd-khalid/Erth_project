from django.urls import path
from . import views

app_name = 'administration'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('heir/<int:heir_id>/create_case/', views.create_case_for_heir, name='create_case_for_heir'),
    path('heir/<int:heir_id>/assign_existing/', views.assign_to_existing_case, name='assign_to_existing_case'),
    path('judges/', views.judge_list, name='judge_list'),
    path('judges/<int:judge_id>/approve/', views.approve_judge, name='approve_judge'),
    path('judges/<int:judge_id>/reject/', views.reject_judge, name='reject_judge'),
]
