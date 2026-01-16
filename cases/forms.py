from django import forms
from .models import Case, Deceased, Asset, Debt, Will

class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = ['case_number']
        widgets = {
            'case_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

class DeceasedForm(forms.ModelForm):
    class Meta:
        model = Deceased
        fields = ['name', 'date_of_death', 'national_id']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_death': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['description', 'value', 'asset_type', 'image']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'وصف الأصل'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'القيمة'}),
            'asset_type': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }

class DebtForm(forms.ModelForm):
    class Meta:
        model = Debt
        fields = ['description', 'amount']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'وصف الدين'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'المبلغ'}),
        }

class WillForm(forms.ModelForm):
    class Meta:
        model = Will
        fields = ['description', 'amount']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'وصف الوصية'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'المبلغ'}),
        }
