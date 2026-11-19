import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Unidade, Usuario, VinculoUnidade

CAMPO_TEXTO = {"class": "field"}


def validar_telefone(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) not in (10, 11):
        raise ValidationError("Informe o celular com DDD, ex.: (47) 99999-0000.")
    return valor.strip()


class TelefoneForm(forms.Form):
    telefone = forms.CharField(
        label="Celular (WhatsApp)",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                **CAMPO_TEXTO,
                "inputmode": "tel",
                "autocomplete": "tel",
                "placeholder": "(47) 99999-0000",
            }
        ),
        help_text="Usamos este número para avisos da reserva no WhatsApp.",
    )

    def clean_telefone(self):
        return validar_telefone(self.cleaned_data["telefone"])


class ConviteForm(forms.Form):
    unidade = forms.ModelChoiceField(
        label="Unidade",
        queryset=Unidade.objects.none(),
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )
    papel = forms.ChoiceField(
        label="Papel",
        choices=VinculoUnidade.Papel.choices,
        initial=VinculoUnidade.Papel.MORADOR,
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )

    def __init__(self, *args, condominio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = Unidade.objects.filter(
            condominio=condominio
        ).order_by("bloco", "numero")


class CadastroConviteForm(forms.Form):
    nome = forms.CharField(
        label="Nome completo", max_length=150, widget=forms.TextInput(attrs=CAMPO_TEXTO)
    )
    username = forms.CharField(
        label="Usuário", max_length=150, widget=forms.TextInput(attrs=CAMPO_TEXTO)
    )
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs=CAMPO_TEXTO))
    telefone = forms.CharField(
        label="Celular (WhatsApp)",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                **CAMPO_TEXTO,
                "inputmode": "tel",
                "autocomplete": "tel",
                "placeholder": "(47) 99999-0000",
            }
        ),
        help_text="Obrigatório para receber os avisos da reserva.",
    )
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={**CAMPO_TEXTO, "autocomplete": "new-password"}),
    )
    confirmar_senha = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={**CAMPO_TEXTO, "autocomplete": "new-password"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if Usuario.objects.filter(username__iexact=username).exists():
            raise ValidationError("Este usuário já existe.")
        return username

    def clean_telefone(self):
        return validar_telefone(self.cleaned_data["telefone"])

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Este e-mail já está cadastrado.")
        return email

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get("senha")
        confirmacao = cleaned.get("confirmar_senha")
        if senha and confirmacao and senha != confirmacao:
            self.add_error("confirmar_senha", "As senhas não conferem.")
        if senha:
            try:
                validate_password(senha)
            except ValidationError as erro:
                self.add_error("senha", erro)
        return cleaned

