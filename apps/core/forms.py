from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify

from apps.reservas.models import Local
from apps.usuarios.forms import CadastroConviteForm
from apps.usuarios.models import Unidade

from .models import Condominio, ConfiguracaoCondominio

CAMPO_TEXTO = {"class": "field"}
CAMPO_CHECKBOX = {"class": "h-4 w-4 rounded border-line text-lagoon"}


class EntrarForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuário",
        widget=forms.TextInput(attrs={**CAMPO_TEXTO, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={**CAMPO_TEXTO, "autocomplete": "current-password"}
        ),
    )


class ConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoCondominio
        fields = [
            "antecedencia_minima_horas",
            "antecedencia_maxima_dias",
            "prazo_analise_horas",
            "politica_prazo_analise",
            "horas_para_reenvio",
            "limite_reservas_mes",
            "pix_dinamico_ativo",
            "pix_gateway",
            "auto_confirmar_ocr",
            "pix_chave",
            "pix_beneficiario",
            "pix_cidade",
            "whatsapp_url",
            "telegram_ativo",
            "telegram_chat_id",
            "cor_primaria",
            "cor_acento",
        ]
        widgets = {
            "politica_prazo_analise": forms.Select(attrs=CAMPO_TEXTO),
            "pix_gateway": forms.Select(attrs=CAMPO_TEXTO),
            "pix_dinamico_ativo": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
            "auto_confirmar_ocr": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
            "telegram_ativo": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
            "whatsapp_url": forms.URLInput(
                attrs={**CAMPO_TEXTO, "placeholder": "https://wa.me/5511999999999"}
            ),
            "pix_chave": forms.TextInput(
                attrs={**CAMPO_TEXTO, "placeholder": "e-mail, telefone, CPF/CNPJ ou aleatória"}
            ),
            "pix_beneficiario": forms.TextInput(attrs={**CAMPO_TEXTO, "maxlength": 25}),
            "pix_cidade": forms.TextInput(attrs={**CAMPO_TEXTO, "maxlength": 15}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome in {
                "pix_dinamico_ativo",
                "auto_confirmar_ocr",
                "telegram_ativo",
                "politica_prazo_analise",
                "pix_gateway",
            }:
                continue
            campo.widget.attrs.setdefault("class", "field")


CAMPO_ARQUIVO = {
    "class": (
        "block w-full text-sm text-muted file:mr-4 file:rounded-full file:border-0 "
        "file:bg-lagoon file:px-4 file:py-2 file:text-sm file:font-semibold file:text-paper"
    )
}


class LocalForm(forms.ModelForm):
    class Meta:
        model = Local
        fields = [
            "nome",
            "categoria",
            "descricao",
            "capacidade",
            "valor",
            "foto",
            "ordem",
            "ativo",
        ]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3, "class": "field"}),
            "categoria": forms.Select(attrs=CAMPO_TEXTO),
            "valor": forms.NumberInput(
                attrs={**CAMPO_TEXTO, "step": "0.01", "inputmode": "decimal", "min": "0"}
            ),
            "capacidade": forms.NumberInput(attrs={**CAMPO_TEXTO, "min": "0"}),
            "ordem": forms.NumberInput(attrs={**CAMPO_TEXTO, "min": "0"}),
            "foto": forms.ClearableFileInput(attrs={"accept": "image/*", **CAMPO_ARQUIVO}),
            "ativo": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome == "ativo":
                continue
            campo.widget.attrs.setdefault("class", "field")


class UnidadeForm(forms.ModelForm):
    class Meta:
        model = Unidade
        fields = ["bloco", "numero"]
        widgets = {
            "bloco": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "A (opcional)"}),
            "numero": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "101"}),
        }

    def __init__(self, *args, condominio=None, **kwargs):
        self.condominio = condominio
        super().__init__(*args, **kwargs)

    def clean(self):
        dados = super().clean()
        numero = dados.get("numero")
        if self.condominio and numero:
            repetidas = Unidade.objects.filter(
                condominio=self.condominio,
                bloco=dados.get("bloco", ""),
                numero=numero,
            )
            if self.instance.pk:
                repetidas = repetidas.exclude(pk=self.instance.pk)
            if repetidas.exists():
                raise forms.ValidationError("Esta unidade já está cadastrada.")
        return dados


class IdentidadeForm(forms.ModelForm):
    class Meta:
        model = Condominio
        fields = ["nome", "logo"]
        widgets = {
            "nome": forms.TextInput(attrs=CAMPO_TEXTO),
            "logo": forms.ClearableFileInput(
                attrs={"accept": "image/*", **CAMPO_ARQUIVO}
            ),
        }


class NovoCondominioForm(forms.ModelForm):
    class Meta:
        model = Condominio
        fields = ["nome", "slug"]
        widgets = {
            "nome": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "Condomínio Jardim"}),
            "slug": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "jardim"}),
        }
        help_texts = {"slug": "Endereço curto, por exemplo bela-vista."}


class OnboardingForm(CadastroConviteForm):
    """Cadastro público: cria o condomínio, a primeira unidade e a conta do síndico."""

    condominio = forms.CharField(
        label="Nome do condomínio",
        max_length=120,
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "Condomínio Jardim das Flores"}
        ),
    )
    slug = forms.SlugField(
        label="Endereço do condomínio",
        max_length=60,
        required=False,
        help_text="Vira /c/endereco/. Em branco, criamos a partir do nome.",
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "jardim-das-flores"}
        ),
    )
    bloco = forms.CharField(
        label="Bloco (opcional)",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "A"}),
    )
    numero = forms.CharField(
        label="Sua unidade",
        max_length=20,
        widget=forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "101"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].label = "Seu nome"
        self.fields["senha"].help_text = "Use ao menos 8 caracteres."
        self.order_fields(
            [
                "condominio",
                "slug",
                "nome",
                "username",
                "email",
                "telefone",
                "bloco",
                "numero",
                "senha",
                "confirmar_senha",
            ]
        )

    def clean_slug(self):
        slug = self.cleaned_data.get("slug") or ""
        slug = slugify(slug)
        if slug and Condominio.objects.filter(slug=slug).exists():
            raise forms.ValidationError("Este endereço já está em uso. Escolha outro.")
        return slug

    def clean_numero(self):
        numero = (self.cleaned_data.get("numero") or "").strip()
        if not numero:
            raise forms.ValidationError("Informe o número da sua unidade.")
        return numero
