from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', _('مدير النظام')
        JUDGE = 'JUDGE', _('قاضي')
        CLERK = 'CLERK', _('كاتب مساعد')
        HEIR = 'HEIR', _('وريث')
        PUBLIC = 'PUBLIC', _('مستخدم عام')

    class VerificationStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد الانتظار')
        APPROVED = 'APPROVED', _('مقبول')
        REJECTED = 'REJECTED', _('مرفوض')

    class ClerkJudgeStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار الموافقة')
        APPROVED = 'APPROVED', _('مقبول')
        REJECTED = 'REJECTED', _('مرفوض')

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PUBLIC)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        verbose_name=_('حالة التحقق')
    )
    
    # New fields for specific roles
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('الاسم الكامل'))
    document_file = models.FileField(upload_to='documents/', blank=True, null=True, verbose_name=_('وثيقة إثبات (حصر ورثة/هوية)'))
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('الاسم الكامل'))
    document_file = models.FileField(upload_to='documents/', blank=True, null=True, verbose_name=_('وثيقة إثبات (حصر ورثة/هوية)'))
    judge_license = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('رقم رخصة القاضي'))
    assigned_judge = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_clerks', limit_choices_to={'role': 'JUDGE'}, verbose_name=_('القاضي المشرف'))
    clerk_judge_status = models.CharField(
        max_length=20,
        choices=ClerkJudgeStatus.choices,
        default=ClerkJudgeStatus.PENDING,
        verbose_name=_('حالة الارتباط بالقاضي')
    )
    
    # Heir specific field
    deceased_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('اسم المتوفى'))

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
