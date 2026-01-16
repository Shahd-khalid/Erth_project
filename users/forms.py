from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

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
        fields = ('username', 'email', 'full_name', 'phone_number', 'deceased_name', 'document_file')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'deceased_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المتوفى لربطك بالقضية الصحيحة'}),
            'document_file': forms.FileInput(attrs={'class': 'form-control'}),
        }

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
