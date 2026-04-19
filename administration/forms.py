from django import forms
from .models import FiqhBook

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
