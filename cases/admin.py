from django.contrib import admin
from .models import CaseAuditLog, Case

# Register your models here.
@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('case_number', 'judge', 'status', 'judge_acceptance_status', 'rejection_reason', 'created_at')
    list_filter = ('status', 'judge_acceptance_status')
    search_fields = ('case_number',)

admin.site.register(CaseAuditLog)
