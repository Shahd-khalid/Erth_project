from django.urls import path
from . import views

app_name = 'heirs'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('session/<uuid:link>/', views.session_lobby, name='session_lobby'),
    path('session/<uuid:link>/<int:heir_id>/', views.session_home, name='session_home'),
    path('session/<uuid:link>/<int:heir_id>/select/', views.select_assets, name='select_assets'),
    path('session/<uuid:link>/<int:heir_id>/reselect/', views.reselect_assets, name='reselect_assets'),
    path('case/<int:case_id>/<int:heir_id>/report/', views.final_report, name='final_report'),
    path('my-assets-sale/', views.my_assets_for_sale, name='my_assets_for_sale'),
    path('manage-listing/<int:component_id>/', views.manage_asset_listing, name='manage_asset_listing'),
    path('settlement/<int:settlement_id>/confirm_sent/', views.confirm_payment_sent, name='confirm_payment_sent'),
    path('settlement/<int:settlement_id>/confirm_receipt/', views.confirm_receipt, name='confirm_receipt'),
]
