from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.reservas.forms import ComprovanteForm
from apps.reservas.models import Local
from apps.usuarios.forms import CadastroConviteForm
from apps.usuarios.models import Unidade

from .models import Condominio, ConfiguracaoCondominio, Plano
from .seguranca import bloqueado, chave_tentativas, limpar, registrar_falha

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

    def clean(self):
        chave = chave_tentativas(self.request, self.data.get("username", ""))
        if bloqueado(chave):
            raise ValidationError(
                "Muitas tentativas de login. Aguarde 15 minutos e tente de novo.",
                code="login_bloqueado",
            )
        try:
            dados = super().clean()
        except ValidationError:
            registrar_falha(chave)
            raise
        limpar(chave)
        return dados


class ConfiguracaoForm(forms.ModelForm):
    pix_api_key = forms.CharField(
        label="Chave de API da AbacatePay",
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "field", "autocomplete": "off", "placeholder": "abc_dev_..."}
        ),
        help_text="Cole a chave da sua conta. Ela fica criptografada e não aparece de novo.",
    )

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
            "pix_chave",
            "pix_beneficiario",
            "pix_cidade",
            "whatsapp_url",
            "whatsapp_numero",
            "telegram_ativo",
            "telegram_chat_id",
            "cor_primaria",
            "cor_acento",
        ]
        widgets = {
            "politica_prazo_analise": forms.Select(attrs=CAMPO_TEXTO),
            "pix_gateway": forms.Select(attrs=CAMPO_TEXTO),
            "pix_dinamico_ativo": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
            "telegram_ativo": forms.CheckboxInput(attrs=CAMPO_CHECKBOX),
            "whatsapp_url": forms.URLInput(
                attrs={**CAMPO_TEXTO, "placeholder": "https://wa.me/5511999999999"}
            ),
            "whatsapp_numero": forms.TextInput(
                attrs={**CAMPO_TEXTO, "placeholder": "(47) 99999-0000"}
            ),
            "pix_chave": forms.TextInput(
                attrs={**CAMPO_TEXTO, "placeholder": "e-mail, telefone, CPF/CNPJ ou aleatória"}
            ),
            "pix_beneficiario": forms.TextInput(
                attrs={
                    **CAMPO_TEXTO,
                    "maxlength": 60,
                    "placeholder": "Nome completo do titular da conta",
                }
            ),
            "pix_cidade": forms.TextInput(attrs={**CAMPO_TEXTO, "maxlength": 15}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pix_gateway"].choices = [
            ("", "---------"),
            (
                ConfiguracaoCondominio.GatewayPix.ABACATEPAY,
                ConfiguracaoCondominio.GatewayPix.ABACATEPAY.label,
            ),
        ]
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

    def clean(self):
        dados = super().clean()
        if not dados.get("pix_dinamico_ativo"):
            return dados

        gateway = dados.get("pix_gateway") or ""
        if gateway != ConfiguracaoCondominio.GatewayPix.ABACATEPAY:
            self.add_error(
                "pix_gateway",
                "Por enquanto o Pix automático está disponível apenas com a AbacatePay.",
            )
        chave_nova = (dados.get("pix_api_key") or "").strip()
        chave_atual = (
            self.instance.pix_gateway_api_key
            if getattr(self.instance, "pk", None)
            else ""
        )
        if not chave_nova and not chave_atual:
            self.add_error(
                "pix_api_key", "Informe a chave de API da sua conta AbacatePay."
            )
        return dados

    def save(self, commit=True):
        configuracao = super().save(commit=False)
        chave = (self.cleaned_data.get("pix_api_key") or "").strip()
        if chave:
            configuracao.pix_gateway_api_key = chave
        if commit:
            configuracao.save()
        return configuracao


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
        fields = ["bloco", "numero", "limite_reservas_mes"]
        widgets = {
            "bloco": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "A (opcional)"}),
            "numero": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "101"}),
            "limite_reservas_mes": forms.NumberInput(
                attrs={**CAMPO_TEXTO, "min": 0, "placeholder": "Padrão do condomínio"}
            ),
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
        fields = ["nome", "logo", "quantidade_unidades"]
        labels = {
            "quantidade_unidades": "Quantidade de unidades",
        }
        help_texts = {
            "quantidade_unidades": (
                "Lotes, apartamentos ou casas. Usamos para sugerir o plano; "
                "0 conta as unidades cadastradas."
            ),
        }
        widgets = {
            "nome": forms.TextInput(attrs=CAMPO_TEXTO),
            "quantidade_unidades": forms.NumberInput(attrs={**CAMPO_TEXTO, "min": 0}),
            "logo": forms.ClearableFileInput(
                attrs={"accept": "image/*", **CAMPO_ARQUIVO}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantidade_unidades"].required = False

    def clean_quantidade_unidades(self):
        return self.cleaned_data.get("quantidade_unidades") or 0


def slug_condominio_unico(nome: str, digitado: str = "") -> str:
    base = slugify(digitado or nome) or "condominio"
    slug = base
    numero = 2
    while Condominio.objects.filter(slug=slug).exists():
        slug = f"{base}-{numero}"
        numero += 1
    return slug


class NovoCondominioForm(forms.ModelForm):
    slug = forms.CharField(
        label="Endereço curto",
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "jardim"}),
        help_text="Pode digitar por extenso. Em branco, criamos a partir do nome.",
    )

    class Meta:
        model = Condominio
        fields = ["nome", "slug"]
        widgets = {
            "nome": forms.TextInput(attrs={**CAMPO_TEXTO, "placeholder": "Condomínio Jardim"}),
        }

    def clean_slug(self):
        return slugify(self.cleaned_data.get("slug") or "")

    def save(self, commit=True):
        condominio = super().save(commit=False)
        condominio.slug = slug_condominio_unico(condominio.nome, condominio.slug)
        if commit:
            condominio.save()
        return condominio


class CondominioDoUsuarioForm(forms.Form):
    """Logado: cria um novo condomínio e vincula a conta atual como síndico."""

    nome = forms.CharField(
        label="Nome do condomínio",
        max_length=120,
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "Condomínio Jardim das Flores"}
        ),
    )
    slug = forms.CharField(
        label="Endereço curto (opcional)",
        max_length=60,
        required=False,
        help_text="Pode digitar por extenso. Em branco, criamos a partir do nome.",
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "jardim-das-flores"}
        ),
    )
    dispositivo = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.HiddenInput(attrs={"data-dispositivo": ""}),
    )

    def clean_slug(self):
        return slugify(self.cleaned_data.get("slug") or "")


class OnboardingForm(CadastroConviteForm):
    """Cadastro público: cria o condomínio e a conta do síndico."""

    condominio = forms.CharField(
        label="Nome do condomínio",
        max_length=120,
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "Condomínio Jardim das Flores"}
        ),
    )
    slug = forms.CharField(
        label="Endereço curto (opcional)",
        max_length=60,
        required=False,
        help_text="Pode digitar por extenso. Em branco, criamos a partir do nome.",
        widget=forms.TextInput(
            attrs={**CAMPO_TEXTO, "placeholder": "jardim-das-flores"}
        ),
    )
    dispositivo = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.HiddenInput(attrs={"data-dispositivo": ""}),
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
                "senha",
                "confirmar_senha",
            ]
        )

    def clean_slug(self):
        return slugify(self.cleaned_data.get("slug") or "")

class PagamentoPlanoForm(ComprovanteForm):
    plano = forms.ModelChoiceField(
        label="Plano escolhido",
        queryset=Plano.objects.none(),
        empty_label=None,
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )
    dia_vencimento = forms.TypedChoiceField(
        label="Dia do vencimento",
        choices=[(dia, f"Dia {dia} de cada mês") for dia in range(1, 29)],
        coerce=int,
        empty_value=None,
        help_text="Escolha um dia entre 1 e 28. O acesso continua por 5 dias após o vencimento.",
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )

    def __init__(self, *args, condominio=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils import timezone

        self.fields["plano"].queryset = Plano.objects.filter(ativo=True).order_by(
            "ordem", "preco_mensal"
        )
        self.fields["comprovante"].label = "Comprovante do Pix"
        if condominio and not self.is_bound:
            self.fields["dia_vencimento"].initial = (
                condominio.dia_vencimento
                or (condominio.vencimento_em and condominio.vencimento_em.day)
                or min(timezone.localdate().day, 28)
            )
