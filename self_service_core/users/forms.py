# --- Import Django ---

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model


User = get_user_model()

# --- Forms ---
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="E-Mail oder Benutzername",
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "name@firma.de",
        }),
    )
    password = forms.CharField(
        label="Passwort",
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "placeholder": "••••••••",
        }),
    )


class CustomerRegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Passwort",
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "••••••••"}),
    )
    password2 = forms.CharField(
        label="Passwort wiederholen",
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "••••••••"}),
    )

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "input", "placeholder": "Benutzername"}),
            "email": forms.EmailInput(attrs={"class": "input", "placeholder": "name@firma.de"}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Die Passwörter stimmen nicht überein.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
        }
