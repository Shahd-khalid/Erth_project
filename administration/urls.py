from django.urls import path
from . import views

app_name = 'administration'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('verification/', views.verification_hub, name='verification_hub'),
    path('cases/', views.case_tracking, name='case_tracking'),
    path('cases/create/', views.create_case, name='create_case'),
    path('cases/<int:case_id>/edit/', views.edit_case, name='edit_case'),
    path('cases/<int:case_id>/delete/', views.delete_case, name='delete_case'),
    path('market/', views.market_oversight, name='market_oversight'),
    path('heirs/', views.heirs_management, name='heirs_management'),
    path('reports/', views.reporting_hub, name='reporting_hub'),
    path('feedback/', views.feedback_list, name='feedback_list'),
    path('settings/', views.admin_settings, name='settings'),
    path('heir/<int:heir_id>/create_case/', views.create_case_for_heir, name='create_case_for_heir'),
    path('heir/<int:heir_id>/assign_existing/', views.assign_to_existing_case, name='assign_to_existing_case'),
    path('heir/<int:heir_id>/reassign/', views.reassign_heir, name='reassign_heir'),
    path('judges/', views.judge_list, name='judge_list'),
    path('users/<int:user_id>/approve/', views.approve_user, name='approve_user'),
    path('users/<int:user_id>/reject/', views.reject_user, name='reject_user'),
    path('marketplace/toggle/<int:listing_id>/', views.toggle_listing, name='toggle_listing'),
    path('export/csv/', views.export_cases_csv, name='export_csv'),
    path('export/print/', views.report_print_view, name='report_print'),
    path('users/management/', views.user_management, name='user_management'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/<int:user_id>/promote/', views.promote_to_admin, name='promote_to_admin'),
    path('users/<int:user_id>/demote/', views.demote_user, name='demote_user'),
    path('users/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('notifications/<int:notif_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('books/upload/', views.upload_fiqh_book, name='upload_book'),
    path('books/<int:book_id>/edit/', views.edit_fiqh_book, name='edit_book'),
    path('books/<int:book_id>/delete/', views.delete_fiqh_book, name='delete_book'),
]
