from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Feedback, User

class GeneralUserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PUBLIC
        if commit:
            user.save()
        return user

class JudgeRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number', 'judge_license')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'judge_license': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.JUDGE
        if commit:
            user.save()
        return user

class HeirRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number', 'gender', 'deceased_name', 'relationship_to_deceased', 'document_file')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'deceased_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المتوفى لربطك بالقضية الصحيحة'}),
            'relationship_to_deceased': forms.Select(attrs={'class': 'form-control'}),
            'document_file': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from cases.models import Heir
        self.fields['relationship_to_deceased'] = forms.ChoiceField(
            choices=Heir.Relationship.choices,
            widget=forms.Select(attrs={'class': 'form-control'}),
            label="صلة القرابة بالمتوفى"
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.HEIR
        if commit:
            user.save()
        return user

class ClerkRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CLERK
        if commit:
            user.save()
        return user


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ('message', 'rating')
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'feedback-textarea',
                'rows': 6,
                'placeholder': 'اكتب ملاحظتك أو تقييمك هنا...',
            }),
            'rating': forms.Select(attrs={'class': 'feedback-select'}),
        }
        labels = {
            'message': 'الرسالة / الملاحظة',
            'rating': 'التقييم بالنجوم',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rating'].required = False
        self.fields['rating'].empty_label = 'بدون تقييم'
