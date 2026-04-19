from django.conf import settings
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

    class Gender(models.TextChoices):
        MALE = 'ذكر', _('ذكر')
        FEMALE = 'أنثى', _('أنثى')

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PUBLIC)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True, verbose_name=_('صورة الملف الشخصي'))
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        verbose_name=_('حالة التحقق')
    )
    
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
    
    # Heir specific fields
    deceased_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('اسم المتوفى'))
    relationship_to_deceased = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('صلة القرابة بالمتوفى'))
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True, null=True, verbose_name=_('الجنس'))
    previous_role = models.CharField(max_length=20, choices=Role.choices, blank=True, null=True, verbose_name=_('الدور السابق'))

    # Admin/Court specific fields
    court_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('اسم المحكمة/المنظمة'))
    court_address = models.TextField(blank=True, null=True, verbose_name=_('العنوان الرسمي'))
    official_stamp = models.ImageField(upload_to='stamps/', blank=True, null=True, verbose_name=_('الختم الرسمي'))

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Feedback(models.Model):
    class Rating(models.IntegerChoices):
        ONE = 1, _('1 نجمة')
        TWO = 2, _('2 نجمتان')
        THREE = 3, _('3 نجوم')
        FOUR = 4, _('4 نجوم')
        FIVE = 5, _('5 نجوم')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback_entries',
        verbose_name=_('المستخدم'),
    )
    message = models.TextField(verbose_name=_('الرسالة / الملاحظة'))
    rating = models.PositiveSmallIntegerField(
        choices=Rating.choices,
        blank=True,
        null=True,
        verbose_name=_('التقييم'),
    )
    date_created = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإرسال'))

    class Meta:
        ordering = ['-date_created']
        verbose_name = _('تقييم وملاحظة')
        verbose_name_plural = _('التقييمات والملاحظات')

    def __str__(self):
        rating_display = f' - {self.rating}/5' if self.rating else ''
        return f'{self.user.username}{rating_display}'
