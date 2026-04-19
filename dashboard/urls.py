from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='index'),
    path('simulator/', views.simulator, name='visual_guide_selection'),
    path('simulator/tree/', views.inheritance_tree, name='inheritance_tree'),
    path('simulator/table/', views.inheritance_table, name='inheritance_table'),
    path('help/', views.help_page, name='help'),
    path('library/', views.fiqh_library, name='library'),
]
