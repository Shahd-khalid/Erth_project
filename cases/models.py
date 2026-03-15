from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid

class Case(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار القاضي')
        ASSIGNED_TO_JUDGE = 'ASSIGNED_TO_JUDGE', _('مقبولة (عند القاضي)')
        WITH_CLERK = 'WITH_CLERK', _('عند الكاتب (إدخال البيانات)')
        DATA_REVIEW = 'DATA_REVIEW', _('مراجعة البيانات (عند القاضي)')
        READY_FOR_CALCULATION = 'READY_FOR_CALCULATION', _('جاهزة للحساب')
        SESSION_ACTIVE = 'SESSION_ACTIVE', _('جلسة توزيع التركة جارية')
        CONSENT_PENDING = 'CONSENT_PENDING', _('بانتظار موافقة الورثة (طلب تراضي)')
        MUTUAL_SELECTION = 'MUTUAL_SELECTION', _('مرحلة التراضي (اختيار الأصول)')
        ALTERNATIVE_SELECTION = 'ALTERNATIVE_SELECTION', _('مرحلة الاعتراض (اختيار بديل)')
        RAFFLE_PHASE = 'RAFFLE_PHASE', _('مرحلة القرعة للنزاعات')
        PAYMENTS_PHASE = 'PAYMENTS_PHASE', _('مرحلة السداد والتخارج (لوحة القاضي)')
        COMPLETED = 'COMPLETED', _('مكتملة')

    class JudgeAcceptanceStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار القبول')
        ACCEPTED = 'ACCEPTED', _('مقبولة')
        REJECTED = 'REJECTED', _('مرفوضة')

    case_number = models.CharField(max_length=50, unique=False, verbose_name=_('رقم القضية'))
    judge = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='judged_cases', limit_choices_to={'role': 'JUDGE'}, verbose_name=_('القاضي'))
    clerk = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='clerked_cases', limit_choices_to={'role': 'CLERK'}, verbose_name=_('الكاتب المساعد'))
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, verbose_name=_('الحالة'))
    judge_acceptance_status = models.CharField(
        max_length=20, 
        choices=JudgeAcceptanceStatus.choices, 
        default=JudgeAcceptanceStatus.PENDING,
        verbose_name=_('حالة قبول القاضي')
    )
    session_link = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name=_('رابط الجلسة'))
    is_ready_for_calculation = models.BooleanField(default=False, verbose_name=_('جاهزة للحساب'))
    
    # New approval flag for Mutual Consent
    judge_consents_to_mutual = models.BooleanField(default=False, verbose_name=_('موافقة القاضي على القسمة بالتراضي'))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        unique_together = ('case_number', 'judge')
        verbose_name = _('القضية')
        verbose_name_plural = _('القضايا')

    def __str__(self):
        return self.case_number

class Deceased(models.Model):
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name='deceased', verbose_name=_('القضية'))
    name = models.CharField(max_length=255, verbose_name=_('اسم المتوفى'))
    date_of_death = models.DateField(verbose_name=_('تاريخ الوفاة'))
    national_id = models.CharField(max_length=20, verbose_name=_('رقم الهوية'))

    def __str__(self):
        return self.name

class Asset(models.Model):
    class AssetType(models.TextChoices):
        REAL_ESTATE = 'عقار', _('عقار')
        CASH = 'نقد', _('نقد')
        STOCK = 'أسهم', _('أسهم')
        OTHER = 'أخرى', _('أخرى')

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='assets', verbose_name=_('القضية'))
    description = models.CharField(max_length=255, verbose_name=_('الوصف'))
    value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('القيمة'))
    image = models.ImageField(upload_to='assets/', blank=True, null=True, verbose_name=_('صورة الأصل'))
    asset_type = models.CharField(max_length=20, choices=AssetType.choices, default=AssetType.OTHER, verbose_name=_('نوع الأصل'))
    
    # Allocation Fields
    assigned_to = models.ForeignKey('Heir', on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_assets', verbose_name=_('مخصص لـ'))
    is_locked = models.BooleanField(default=False, verbose_name=_('مقفل (تم الاختيار)'))


    def __str__(self):
        return f"{self.description} - {self.value}"

class Debt(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='debts', verbose_name=_('القضية'))
    description = models.CharField(max_length=255, verbose_name=_('وصف الدين'))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('المبلغ'))

    def __str__(self):
        return f"{self.description} - {self.amount}"

class Will(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='wills', verbose_name=_('القضية'))
    description = models.CharField(max_length=255, verbose_name=_('وصف الوصية'))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('المبلغ'))

    def __str__(self):
        return f"{self.description} - {self.amount}"

class Heir(models.Model):
    class Relationship(models.TextChoices):
        HUSBAND = 'زوج', _('زوج')
        WIFE = 'زوجة', _('زوجة')
        SON = 'ابن', _('ابن')
        DAUGHTER = 'بنت', _('بنت')
        FATHER = 'أب', _('أب')
        MOTHER = 'أم', _('أم')
        BROTHER = 'أخ شقيق', _('أخ شقيق')
        SISTER = 'أخت شقيقة', _('أخت شقيقة')
        
        # Second Level Descendants (Grandchildren)
        SON_OF_SON = 'ابن ابن', _('ابن ابن')
        DAUGHTER_OF_SON = 'بنت ابن', _('بنت ابن')
        
        # Ascendants (Grandparents - Paternal most relevant for Hajb usually, keeping generic for now or specific)
        GRANDFATHER_FATHER = 'جد (أبو الأب)', _('جد (أبو الأب)')
        GRANDMOTHER_FATHER = 'جدة (أم الأب)', _('جدة (أم الأب)')
        GRANDMOTHER_MOTHER = 'جدة (أم الأم)', _('جدة (أم الأم)')
        
        # Siblings (Paternal/Maternal)
        BROTHER_FATHER = 'أخ لأب', _('أخ لأب')
        SISTER_FATHER = 'أخت لأب', _('أخت لأب')
        BROTHER_MOTHER = 'أخ لأم', _('أخ لأم')
        SISTER_MOTHER = 'أخت لأم', _('أخت لأم')
        
        # Nephews (Sons of Brothers) - Only males inherit as Asabah
        SON_OF_BROTHER = 'ابن أخ شقيق', _('ابن أخ شقيق')
        SON_OF_BROTHER_FATHER = 'ابن أخ لأب', _('ابن أخ لأب')
        
        # Uncles (Paternal)
        UNCLE = 'عم شقيق', _('عم شقيق')
        UNCLE_FATHER = 'عم لأب', _('عم لأب')
        
        # Cousins (Sons of Uncles)
        SON_OF_UNCLE = 'ابن عم شقيق', _('ابن عم شقيق')
        SON_OF_UNCLE_FATHER = 'ابن عم لأب', _('ابن عم لأب')

    class Gender(models.TextChoices):
        MALE = 'ذكر', _('ذكر')
        FEMALE = 'أنثى', _('أنثى')

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='heirs', verbose_name=_('القضية'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='heir_records', verbose_name=_('حساب المستخدم'))
    name = models.CharField(max_length=255, verbose_name=_('الاسم'))
    relationship = models.CharField(max_length=50, choices=Relationship.choices, verbose_name=_('صلة القرابة'))
    gender = models.CharField(max_length=10, choices=Gender.choices, verbose_name=_('الجنس'))
    is_blocked = models.BooleanField(default=False, verbose_name=_('محجوب'))
    blocking_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('سبب الحجب'))
    
    # Session Fields
    share_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_('نسبة الإرث %'))
    share_value = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_('قيمة النصيب'))
    allocated_share = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_('القيمة المخصصة'))
    
    class AcceptanceStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد الانتظار')
        ACCEPTED = 'ACCEPTED', _('موافق (انتهاء)')
        REJECTED = 'REJECTED', _('غير موافق (اعتراض)')
        
    class MutualConsentStatus(models.TextChoices):
        NOT_VOTED = 'NOT_VOTED', _('لم يصوت')
        AGREED = 'AGREED', _('موافق على القسمة بالتراضي')
        DISAGREED = 'DISAGREED', _('غير موافق على القسمة بالتراضي')
        
    acceptance_status = models.CharField(max_length=20, choices=AcceptanceStatus.choices, default=AcceptanceStatus.PENDING, verbose_name=_('حالة القبول'))
    mutual_consent_status = models.CharField(max_length=20, choices=MutualConsentStatus.choices, default=MutualConsentStatus.NOT_VOTED, verbose_name=_('حالة التصويت للتراضي'))
    allocation_description = models.TextField(blank=True, verbose_name=_('وصف القسمة (رسالة القاضي)'))

    def remaining_share(self):
        """Return the remaining share value that the heir can still receive."""
        return max(self.share_value - self.allocated_share, 0)

    def can_select(self, amount):
        """Check if the heir can select an asset of given amount without exceeding share."""
        return amount <= self.remaining_share()

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()})"

class HeirAssetSelection(models.Model):
    class SelectionStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد الانتظار')
        ACCEPTED = 'ACCEPTED', _('مقبول')
        REJECTED = 'REJECTED', _('مرفوض')

    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name='selections', verbose_name=_('الوريث'))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='selection_intents', null=True, blank=True, verbose_name=_('الأصل'))
    component = models.ForeignKey('AssetComponent', on_delete=models.CASCADE, related_name='selection_intents', null=True, blank=True, verbose_name=_('جزء الأصل'))
    status = models.CharField(max_length=20, choices=SelectionStatus.choices, default=SelectionStatus.PENDING, verbose_name=_('حالة الاختيار'))
    selected_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_('القيمة المختارة'))
    
    # Financial Pledge Tracking
    requires_pledge = models.BooleanField(default=False, verbose_name=_('يتطلب تعهد مالي'))
    pledge_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name=_('مبلغ التعهد الاضافي'))
    
    # For Alternative Phase
    is_challenging_owner = models.BooleanField(default=False, verbose_name=_('نزاع ضد مالك حالي'))
    
    # Processing status
    is_processed = models.BooleanField(default=False, verbose_name=_('تم معالجته (تحويل لملكية أو نزاع)'))
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('heir', 'asset')
        verbose_name = _('رغبة اختيار أصل')
        verbose_name_plural = _('رغبات اختيار الأصول')

    def __str__(self):
        return f"{self.heir.name} -> {self.asset.description}"

class AssetComponent(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='components', verbose_name=_('الأصل التابع له'))
    description = models.CharField(max_length=255, verbose_name=_('وصف الجزء/العينة'))
    value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('القيمة'))
    assigned_to = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_components', verbose_name=_('مخصص لـ'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('جزء من الأصل')
        verbose_name_plural = _('أجزاء الأصول')

    def __str__(self):
        return f"{self.description} ({self.value}) - {self.asset.description}"

class PublicAssetListing(models.Model):
    component = models.OneToOneField(AssetComponent, on_delete=models.CASCADE, related_name='listing', verbose_name=_('العينة/الأصل'))
    seller_name = models.CharField(max_length=255, verbose_name=_('اسم البائع'))
    seller_email = models.EmailField(verbose_name=_('البريد الإلكتروني'))
    seller_phone = models.CharField(max_length=20, verbose_name=_('رقم التواصل'))
    price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('سعر العرض'))
    description = models.TextField(verbose_name=_('وصف العرض'))
    is_active = models.BooleanField(default=True, verbose_name=_('نشط (يُعرض للبيع)'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ العرض'))

    class Meta:
        verbose_name = _('عرض بيع أصل (عام)')
        verbose_name_plural = _('عروض بيع الأصول (عامة)')

    def __str__(self):
        return f"{self.seller_name} - {self.component.description}"

class DisputeRaffle(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='disputes', verbose_name=_('القضية'))
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_('الأصل المتنازع عليه'))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_('الجزء المتنازع عليه'))
    contenders = models.ManyToManyField(Heir, related_name='raffle_entries', verbose_name=_('المتنازعين'))
    winner = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_raffles', verbose_name=_('الفائز بالقرعة'))
    is_resolved = models.BooleanField(default=False, verbose_name=_('تم حل النزاع (إجراء القرعة)'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('نزاع / قرعة')
        verbose_name_plural = _('النزاعات والقرعات')

    def __str__(self):
        target = self.asset.description if self.asset else self.component.description
        return f"قرعة في قضية {self.case.case_number} على {target}"

class PaymentSettlement(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='settlements', verbose_name=_('القضية'))
    payer = models.ForeignKey(Heir, on_delete=models.CASCADE, related_name='payments_owed', verbose_name=_('الدافع (المتعهد)'))
    original_owner = models.ForeignKey(Heir, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_expected', verbose_name=_('المستلم الأصلي (إن وجد)'))
    
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_('الأصل المرتبط'))
    component = models.ForeignKey(AssetComponent, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_('الجزء المرتبط'))
    
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('المبلغ'))
    
    # Track physical/external payment flow: Payer -> Judge -> Receiver
    heir_confirmed_payment = models.BooleanField(default=False, verbose_name=_('قام الوريث بتأكيد السداد'))
    is_paid_to_judge = models.BooleanField(default=False, verbose_name=_('تم استلام المبلغ من قبل القاضي'))
    is_delivered_to_owner = models.BooleanField(default=False, verbose_name=_('تم تسليم المبلغ للمالك النهائي'))
    
    # Metadata
    reason = models.CharField(max_length=255, verbose_name=_('سبب الدفعة (فرق قيمة، تعويض نزاع)'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('تسوية مالية')
        verbose_name_plural = _('التسويات المالية')

    def __str__(self):
        return f"دفعة من {self.payer.name} بقيمة {self.amount}"

class SelectionLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='selection_logs', verbose_name=_('القضية'))
    heir = models.ForeignKey(Heir, on_delete=models.CASCADE, verbose_name=_('الوريث'))
    action_text = models.TextField(verbose_name=_('نص الإجراء'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('وقت الإجراء'))

    class Meta:
        verbose_name = _('سجل اختيار أصل')
        verbose_name_plural = _('سجلات اختيار الأصول')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.heir.name}: {self.action_text}"
