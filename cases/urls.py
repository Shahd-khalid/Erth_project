from django.urls import path
from . import views

urlpatterns = [
    path('', views.case_list, name='case_list'),
    path('create/', views.create_case, name='create_case'),
    path('<int:case_id>/review/', views.review_distribution, name='review_distribution'),
    path('<int:case_id>/lottery/', views.start_lottery, name='start_lottery'),
    path('<int:case_id>/liquidation/', views.liquidation_view, name='liquidation'),
    path('<int:case_id>/report/', views.final_report, name='final_report'),
]
