from django.contrib import admin
from django.utils.html import format_html

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('rating_number', 'user', 'rating_value', 'rating_stars', 'date_created')
    list_filter = ('rating', 'date_created')
    search_fields = ('user__username', 'user__full_name', 'message')
    readonly_fields = ('date_created',)
    ordering = ('-date_created', '-id')

    @admin.display(description='رقم التقييم', ordering='id')
    def rating_number(self, obj):
        return obj.id

    @admin.display(description='قيمة التقييم', ordering='rating')
    def rating_value(self, obj):
        return obj.rating if obj.rating else 'بدون تقييم'

    @admin.display(description='التقييم')
    def rating_stars(self, obj):
        if not obj.rating:
            return 'بدون تقييم'

        stars = ''.join('★' if index < obj.rating else '☆' for index in range(5))
        return format_html(
            '<span style="color:#d4af37;font-size:1.1rem;letter-spacing:2px;">{}</span>',
            stars,
        )
