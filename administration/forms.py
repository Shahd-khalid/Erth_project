from django import forms
from .models import FiqhBook
from django.contrib.auth import get_user_model
from cases.models import Case, Heir, Deceased

User = get_user_model()

class FiqhBookForm(forms.ModelForm):
    class Meta:
        model = FiqhBook
        fields = ['title', 'author', 'pdf_file', 'cover_image']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'عنوان الكتاب'}),
            'author': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'المؤلف (اختياري)'}),
            'pdf_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
            'cover_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

class AdminUserCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'كلمة المرور'}), label='كلمة المرور')
    
    # New fields for linkage
    selected_case = forms.ModelChoiceField(
        queryset=Case.objects.all(),
        required=False,
        label='القضية المرتبطة (إلزامي للورثة)',
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label='--- اختر القضية المعنية ---'
    )
    
    relationship = forms.ChoiceField(
        choices=Heir.Relationship.choices,
        required=False,
        label='صلة القرابة',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ['role', 'username', 'email', 'full_name', 'phone_number', 'gender', 'judge_license', 'deceased_name']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستخدم للدخول'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'البريد الإلكتروني للإشعارات'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الكامل'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف (اختياري)'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'judge_license': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رخصة القاضي (للقضاة فقط)'}),
            'deceased_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المتوفى (للورثة فقط)'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].choices = [
            (User.Role.JUDGE, 'قاضي'),
            (User.Role.CLERK, 'كاتب مساعد'),
            (User.Role.HEIR, 'وريث'),
        ]
        self.fields['role'].help_text = 'اختر نوع الحساب الذي تود إنشاءه'
        
        # Improve the display label for cases in the dropdown
        # We override the label_from_instance logic for the select widget
        self.fields['selected_case'].label_from_instance = self.get_case_label
        
        self.fields['selected_case'].help_text = 'يجب ربط الوريث بقضية محددة لإتمام العملية.'
        
    def get_case_label(self, obj):
        judge_name = obj.judge.full_name or obj.judge.username if obj.judge else "غير معين"
        try:
            deceased_name = obj.deceased.name
        except:
            deceased_name = "غير مسجل"
        return f"قضية رقم: {obj.display_case_number} | القاضي: {judge_name} | المتوفى: {deceased_name}"

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        selected_case = cleaned_data.get('selected_case')

        if role == User.Role.HEIR and not selected_case:
            self.add_error('selected_case', 'يجب اختيار القضية المرتبطة عند إنشاء حساب وريث.')
            
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        
        # Map relationship to the user model field too for consistency
        if self.cleaned_data.get('role') == User.Role.HEIR:
            user.relationship_to_deceased = self.cleaned_data.get('relationship')
            
        user.is_verified = True
        user.verification_status = User.VerificationStatus.APPROVED
        if commit:
            user.save()
        return user

class AdminCaseCreationForm(forms.ModelForm):
    deceased_name = forms.CharField(max_length=255, label='اسم المتوفى', widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم المتوفى بالكامل'}))
    date_of_death = forms.DateField(label='تاريخ الوفاة', widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    national_id = forms.CharField(max_length=20, label='رقم هوية المتوفى', widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهوية / السجل المدني'}))

    class Meta:
        model = Case
        fields = ['judge', 'inheritance_determination_doc']
        widgets = {
            'judge': forms.Select(attrs={'class': 'form-control'}),
            'inheritance_determination_doc': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show approved judges
        from users.models import User as ProfileUser
        self.fields['judge'].queryset = ProfileUser.objects.filter(role=ProfileUser.Role.JUDGE, verification_status=ProfileUser.VerificationStatus.APPROVED)
        self.fields['judge'].label = 'القاضي المشرف'
        self.fields['judge'].empty_label = "--- اختر القاضي الذي سيستلم القضية ---"
