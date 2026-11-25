from datetime import datetime, timedelta

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.core.permissoes import unidades_para_reserva
from apps.usuarios.models import Unidade

from .models import Local, Reserva

CAMPO_TEXTO = {"class": "field"}
MENSAGEM_BLOQUEIO_RESERVA = (
    "Reservas bloqueadas para este morador. Entre em contato com o administrador "
    "ou síndico para saber o motivo."
)


class ReservaForm(forms.Form):
    data = forms.DateField(
        label="Data",
        widget=forms.DateInput(attrs={**CAMPO_TEXTO, "type": "date"}),
    )
    hora_inicio = forms.TimeField(
        label="Início",
        widget=forms.TimeInput(attrs={**CAMPO_TEXTO, "type": "time"}),
    )
    hora_fim = forms.TimeField(
        label="Término",
        widget=forms.TimeInput(attrs={**CAMPO_TEXTO, "type": "time"}),
    )
    unidade = forms.ModelChoiceField(
        label="Unidade",
        queryset=Unidade.objects.none(),
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )

    def __init__(self, *args, condominio, usuario, local: Local, **kwargs):
        super().__init__(*args, **kwargs)
        self.condominio = condominio
        self.usuario = usuario
        self.local = local
        self.fields["unidade"].queryset = unidades_para_reserva(usuario, condominio)

    def clean(self):
        cleaned = super().clean()
        if "unidade" not in cleaned:
            escolhida = self.data.get("unidade")
            if escolhida and str(escolhida).isdigit():
                bloqueada = Unidade.objects.filter(
                    pk=int(escolhida),
                    condominio=self.condominio,
                    vinculos__usuario=self.usuario,
                    vinculos__ativo=True,
                    vinculos__bloqueio_reservas=True,
                ).exists()
                if bloqueada:
                    self.add_error("unidade", MENSAGEM_BLOQUEIO_RESERVA)
        data = cleaned.get("data")
        hora_inicio = cleaned.get("hora_inicio")
        hora_fim = cleaned.get("hora_fim")
        if not (data and hora_inicio and hora_fim):
            return cleaned

        fuso = timezone.get_current_timezone()
        inicio = timezone.make_aware(datetime.combine(data, hora_inicio), fuso)
        fim = timezone.make_aware(datetime.combine(data, hora_fim), fuso)
        agora = timezone.now()
        configuracao = self.condominio.configuracao

        if fim <= inicio:
            self.add_error("hora_fim", "O término deve ser posterior ao início.")
            return cleaned

        minimo = agora + timedelta(hours=configuracao.antecedencia_minima_horas)
        if inicio < minimo:
            self.add_error(
                "data",
                f"Reserve com pelo menos {configuracao.antecedencia_minima_horas} horas "
                "de antecedência.",
            )

        maximo = agora + timedelta(days=configuracao.antecedencia_maxima_dias)
        if inicio > maximo:
            self.add_error(
                "data",
                f"A reserva pode ser feita com no máximo "
                f"{configuracao.antecedencia_maxima_dias} dias de antecedência.",
            )

        Reserva.objects.filter(
            local=self.local,
            status=Reserva.Status.AGUARDANDO_COMPROVANTE,
            expira_em__lt=agora,
        ).update(status=Reserva.Status.EXPIRADA)

        conflito = (
            Reserva.objects.filter(local=self.local)
            .filter(
                Q(status__in=[Reserva.Status.EM_ANALISE, Reserva.Status.CONFIRMADA])
                | Q(
                    status=Reserva.Status.AGUARDANDO_COMPROVANTE,
                    expira_em__gt=agora,
                )
            )
            .filter(inicio__lt=fim, fim__gt=inicio)
            .exists()
        )
        if conflito:
            self.add_error("hora_inicio", "Este horário já está reservado. Escolha outro.")

        unidade = cleaned.get("unidade")
        limite = configuracao.limite_reservas_mes
        if unidade and unidade.limite_reservas_mes is not None:
            limite = unidade.limite_reservas_mes
        if unidade and limite:
            inicio_mes = timezone.localtime(inicio).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            fim_mes = (inicio_mes + timedelta(days=32)).replace(day=1)
            quantidade = (
                Reserva.objects.filter(
                    unidade=unidade,
                    inicio__gte=inicio_mes,
                    inicio__lt=fim_mes,
                )
                .exclude(status__in=[Reserva.Status.CANCELADA, Reserva.Status.EXPIRADA])
                .count()
            )
            if quantidade >= limite:
                self.add_error(
                    "unidade",
                    f"Esta unidade já atingiu o limite de {limite} "
                    f"reserva{'' if limite == 1 else 's'} em {inicio_mes:%m/%Y}.",
                )

        cleaned["inicio"] = inicio
        cleaned["fim"] = fim
        return cleaned


class ComprovanteForm(forms.Form):
    comprovante = forms.FileField(
        label="Comprovante",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": "image/jpeg,image/png,image/webp,application/pdf",
                "class": "block w-full text-sm text-muted file:mr-4 file:rounded-full "
                "file:border-0 file:bg-lagoon file:px-4 file:py-2 file:text-sm "
                "file:font-semibold file:text-paper",
            }
        ),
    )

    TIPOS = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
    EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    ASSINATURAS = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/webp": (b"RIFF",),
        "application/pdf": (b"%PDF-",),
    }

    def clean_comprovante(self):
        arquivo = self.cleaned_data["comprovante"]
        if arquivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("O arquivo deve ter no máximo 5 MB.")
        if arquivo.content_type not in self.TIPOS:
            raise forms.ValidationError("Envie uma imagem JPG, PNG, WebP ou um PDF.")
        extensao = arquivo.name.lower().rsplit(".", 1)[-1]
        if f".{extensao}" not in self.EXTENSOES:
            raise forms.ValidationError("Extensão de arquivo não permitida.")

        arquivo.seek(0)
        cabecalho = arquivo.read(16)
        arquivo.seek(0)
        if not any(
            cabecalho.startswith(assinatura)
            for assinatura in self.ASSINATURAS[arquivo.content_type]
        ):
            raise forms.ValidationError(
                "O conteúdo do arquivo não corresponde ao formato informado."
            )
        if arquivo.content_type == "image/webp" and cabecalho[8:12] != b"WEBP":
            raise forms.ValidationError(
                "O conteúdo do arquivo não corresponde ao formato informado."
            )
        return arquivo


class ListaEsperaForm(forms.Form):
    data = forms.DateField(
        label="Data",
        widget=forms.DateInput(attrs={**CAMPO_TEXTO, "type": "date"}),
    )
    unidade = forms.ModelChoiceField(
        label="Unidade",
        queryset=Unidade.objects.none(),
        widget=forms.Select(attrs=CAMPO_TEXTO),
    )

    def __init__(self, *args, condominio, usuario, local, **kwargs):
        super().__init__(*args, **kwargs)
        self.condominio = condominio
        self.usuario = usuario
        self.local = local
        self.fields["unidade"].queryset = unidades_para_reserva(usuario, condominio)

    def clean(self):
        cleaned = super().clean()
        if "unidade" not in cleaned:
            escolhida = self.data.get("unidade")
            if escolhida and str(escolhida).isdigit():
                bloqueada = Unidade.objects.filter(
                    pk=int(escolhida),
                    condominio=self.condominio,
                    vinculos__usuario=self.usuario,
                    vinculos__ativo=True,
                    vinculos__bloqueio_reservas=True,
                ).exists()
                if bloqueada:
                    self.add_error("unidade", MENSAGEM_BLOQUEIO_RESERVA)
        return cleaned

    def clean_data(self):
        data = self.cleaned_data["data"]
        if data < timezone.localdate():
            raise forms.ValidationError("Escolha uma data a partir de hoje.")
        return data
