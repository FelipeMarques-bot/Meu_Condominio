import logging
import secrets
from datetime import timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.storage import armazenamento_privado
from apps.reservas.models import Local
from apps.usuarios.forms import CadastroConviteForm, ConviteForm, TelefoneForm
from apps.usuarios.models import Convite, Unidade, Usuario, VinculoUnidade

from .forms import (
    CondominioDoUsuarioForm,
    ConfiguracaoForm,
    EntrarForm,
    IdentidadeForm,
    LocalForm,
    NovoCondominioForm,
    OnboardingForm,
    PagamentoPlanoForm,
    UnidadeForm,
    slug_condominio_unico,
)
from .models import Condominio, PagamentoPlano, Plano
from .notifications import (
    emails_administradores,
    link_whatsapp,
    telegram_configurado,
)
from .permissoes import gestao_required, pode_aprovar, pode_gerir
from .trial import hashes_do_cadastro, trial_ja_usado

logger = logging.getLogger(__name__)


def _condominio(request):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = None
    return condominio


def _aviso_trial_usado() -> str:
    return (
        "Já existe um teste gratuito iniciado com estes dados (rede, celular ou "
        "e-mail) há pouco tempo. Entre na conta existente ou fale com "
        f"{settings.CONTATO_EMAIL} para liberar outro condomínio."
    )


def _slug_unico(condominio, nome: str, ignorar=None) -> str:
    base = slugify(nome) or "espaco"
    slug = base
    numero = 2
    existentes = Local.all_objects.filter(condominio=condominio)
    if ignorar is not None and ignorar.pk:
        existentes = existentes.exclude(pk=ignorar.pk)
    while existentes.filter(slug=slug).exists():
        slug = f"{base}-{numero}"
        numero += 1
    return slug


def _arquivo_pwa(nome: str, content_type: str):
    caminho = Path(settings.BASE_DIR) / "static" / "pwa" / nome
    if not caminho.exists():
        raise Http404("Arquivo do aplicativo não encontrado.")
    return FileResponse(caminho.open("rb"), content_type=content_type)


def manifest(request):
    resposta = _arquivo_pwa("manifest.webmanifest", "application/manifest+json")
    resposta["Cache-Control"] = "public, max-age=3600"
    return resposta


def service_worker(request):
    resposta = _arquivo_pwa("sw.js", "application/javascript")
    resposta["Service-Worker-Allowed"] = "/"
    resposta["Cache-Control"] = "no-cache"
    return resposta


def tarefas_prazos(request, token):
    esperado = settings.TAREFAS_TOKEN
    if not esperado or not secrets.compare_digest(token, esperado):
        raise Http404
    if request.method not in {"GET", "POST"}:
        raise Http404

    from apps.reservas.prazos import processar_prazos

    resultado = processar_prazos()
    return JsonResponse({"ok": True, **resultado})


def landing(request):
    return render(
        request,
        "core/landing.html",
        {
            "planos": Plano.objects.filter(ativo=True),
            "condominio_demo": Condominio.objects.filter(
                slug="bela-vista", ativo=True
            ).first(),
        },
    )


@login_required
def meus_condominios(request):
    vinculos = (
        request.user.vinculos.filter(ativo=True)
        .select_related("unidade__condominio")
        .order_by("unidade__condominio__nome", "pk")
    )
    mapa = {}
    for vinculo in vinculos:
        condominio = vinculo.unidade.condominio
        item = mapa.setdefault(
            condominio.pk,
            {"condominio": condominio, "papeis": [], "unidades": []},
        )
        papel = vinculo.get_papel_display()
        if papel not in item["papeis"]:
            item["papeis"].append(papel)
        if not vinculo.unidade.administrativa:
            item["unidades"].append(vinculo.unidade.rotulo)

    itens = list(mapa.values())
    for item in itens:
        condominio = item["condominio"]
        item["pode_gerir"] = pode_gerir(request.user, condominio)
        item["pode_aprovar"] = pode_aprovar(request.user, condominio)

    return render(
        request,
        "core/meus_condominios.html",
        {"itens": itens},
    )


def criar_condominio(request):
    """Onboarding: condomínio, primeira unidade e conta (ou vínculo) de síndico."""
    if request.user.is_authenticated:
        form = CondominioDoUsuarioForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            dados = form.cleaned_data
            hashes = hashes_do_cadastro(
                request, request.user.telefone, request.user.email
            )
            if trial_ja_usado(hashes):
                form.add_error(None, _aviso_trial_usado())
            else:
                with transaction.atomic():
                    condominio = Condominio.objects.create(
                        nome=dados["nome"],
                        slug=slug_condominio_unico(dados["nome"], dados["slug"]),
                        plano=Plano.para_quantidade(1),
                        trial_ate=timezone.now()
                        + timedelta(days=settings.TRIAL_DIAS),
                        **hashes,
                    )
                    unidade = Unidade.objects.create(
                        condominio=condominio,
                        numero="Administração",
                        administrativa=True,
                    )
                    VinculoUnidade.objects.create(
                        usuario=request.user,
                        unidade=unidade,
                        papel=VinculoUnidade.Papel.SINDICO,
                    )
                messages.success(
                    request,
                    f"{condominio.nome} criado! Você é síndico e tem "
                    f"{settings.TRIAL_DIAS} dias de teste.",
                )
                return redirect("gestao", slug=condominio.slug)
        return render(
            request,
            "core/criar_condominio.html",
            {"form": form, "logado": True},
        )

    form = OnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        hashes = hashes_do_cadastro(request, dados["telefone"], dados["email"])
        if trial_ja_usado(hashes):
            form.add_error(None, _aviso_trial_usado())
        else:
            with transaction.atomic():
                condominio = Condominio.objects.create(
                    nome=dados["condominio"],
                    slug=slug_condominio_unico(dados["condominio"], dados["slug"]),
                    plano=Plano.para_quantidade(1),
                    trial_ate=timezone.now() + timedelta(days=settings.TRIAL_DIAS),
                    **hashes,
                )
                unidade = Unidade.objects.create(
                    condominio=condominio,
                    numero="Administração",
                    administrativa=True,
                )
                usuario = Usuario.objects.create_user(
                    username=dados["username"],
                    email=dados["email"],
                    password=dados["senha"],
                    first_name=dados["nome"],
                    telefone=dados["telefone"],
                )
                VinculoUnidade.objects.create(
                    usuario=usuario,
                    unidade=unidade,
                    papel=VinculoUnidade.Papel.SINDICO,
                )
            login(request, usuario)
            messages.success(
                request,
                f"{condominio.nome} está no ar! Você tem {settings.TRIAL_DIAS} "
                "dias de teste e já entra como síndico.",
            )
            return redirect("gestao", slug=condominio.slug)

    return render(request, "core/criar_condominio.html", {"form": form})


@login_required
def assinatura(request, slug):
    """Status do teste/plano e envio do comprovante de pagamento."""
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        raise Http404("Condomínio não encontrado.")
    if not request.user.vinculos.filter(
        ativo=True, unidade__condominio=condominio
    ).exists():
        raise Http404("Você não tem acesso a este condomínio.")

    gerir = pode_gerir(request.user, condominio)
    pendente = condominio.pagamentos_plano.filter(
        status=PagamentoPlano.Status.PENDENTE
    ).first()
    form = None

    if request.method == "POST":
        if not gerir:
            messages.error(request, "Somente a gestão pode enviar o comprovante.")
            return redirect("assinatura", slug=condominio.slug)
        if pendente:
            messages.info(
                request,
                "Já existe um comprovante aguardando conferência. "
                "Aguarde a liberação.",
            )
            return redirect("assinatura", slug=condominio.slug)
        form = PagamentoPlanoForm(request.POST, request.FILES)
        if form.is_valid():
            plano = form.cleaned_data["plano"]
            PagamentoPlano.objects.create(
                condominio=condominio,
                plano=plano,
                valor=plano.preco_mensal,
                comprovante=form.cleaned_data["comprovante"],
            )
            messages.success(
                request,
                "Comprovante enviado. O acesso será liberado após a conferência.",
            )
            return redirect("assinatura", slug=condominio.slug)

    if form is None:
        form = PagamentoPlanoForm()

    return render(
        request,
        "core/assinatura.html",
        {
            "condominio": condominio,
            "planos": Plano.objects.filter(ativo=True).order_by(
                "ordem", "preco_mensal"
            ),
            "form": form,
            "pendente": pendente,
            "pagamentos": condominio.pagamentos_plano.select_related("plano")[:6],
            "pode_gerir": gerir,
            "dias_assinatura": settings.ASSINATURA_DIAS,
        },
    )


def painel_redirect(request, slug):
    return redirect("agenda", slug=slug)


class EntrarView(LoginView):
    template_name = "core/login.html"
    authentication_form = EntrarForm
    redirect_authenticated_user = True

    def get_success_url(self):
        url = self.get_redirect_url()
        if url:
            return url
        usuario = self.request.user
        if usuario.is_superuser:
            return reverse("plataforma")
        vinculos = list(
            usuario.vinculos.filter(ativo=True)
            .select_related("unidade__condominio")
            .order_by("pk")
        )
        papeis_gestao = {
            VinculoUnidade.Papel.SINDICO,
            VinculoUnidade.Papel.ADMINISTRADORA,
        }
        for vinculo in vinculos:
            if vinculo.papel in papeis_gestao:
                return reverse("gestao", args=[vinculo.unidade.condominio.slug])
        if vinculos:
            return reverse(
                "agenda", args=[vinculos[0].unidade.condominio.slug]
            )
        return reverse("landing")


@login_required
def minha_conta(request, slug):
    condominio = getattr(request, "condominio", None) or get_object_or_404(
        Condominio, slug=slug, ativo=True
    )
    vinculos = (
        request.user.vinculos.filter(ativo=True, unidade__condominio=condominio)
        .select_related("unidade")
        .order_by("unidade__bloco", "unidade__numero")
    )
    form_telefone = TelefoneForm(
        request.POST or None, initial={"telefone": request.user.telefone}
    )
    if request.method == "POST" and form_telefone.is_valid():
        request.user.telefone = form_telefone.cleaned_data["telefone"]
        request.user.save(update_fields=["telefone"])
        messages.success(request, "Celular atualizado. Você receberá os avisos.")
        return redirect("minha_conta", slug=condominio.slug)

    return render(
        request,
        "core/minha_conta.html",
        {
            "condominio": condominio,
            "vinculos": vinculos,
            "form_telefone": form_telefone,
        },
    )


class TrocarSenhaView(PasswordChangeView):
    template_name = "core/senha.html"

    def form_valid(self, form):
        messages.success(self.request, "Senha atualizada com sucesso.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("minha_conta", args=[self.kwargs["slug"]])


def agenda(request, slug):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = get_object_or_404(Condominio, slug=slug, ativo=True)

    locais = Local.objects.filter(condominio=condominio, ativo=True).order_by("ordem", "nome")
    configuracao = getattr(condominio, "configuracao", None)

    return render(
        request,
        "core/agenda.html",
        {
            "condominio": condominio,
            "configuracao": configuracao,
            "locais": locais,
        },
    )


@login_required
@gestao_required
def gestao(request, slug):
    condominio = _condominio(request)

    return render(
        request,
        "core/gestao.html",
        {
            "condominio": condominio,
            "qtd_locais": Local.all_objects.filter(condominio=condominio).count(),
            "qtd_unidades": condominio.quantidade_unidades
            or condominio.unidades.filter(administrativa=False).count(),
            "qtd_convites": Convite.objects.filter(
                condominio=condominio, usado_em__isnull=True
            ).count(),
            "qtd_pendentes": condominio.reservas.filter(
                status="em_analise"
            ).count(),
        },
    )


@login_required
@gestao_required
def configuracoes(request, slug):
    condominio = _condominio(request)
    configuracao = condominio.configuracao
    form = ConfiguracaoForm(request.POST or None, instance=configuracao)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configurações atualizadas.")
        return redirect("configuracoes", slug=condominio.slug)

    webhook_url = request.build_absolute_uri(
        reverse(
            "webhook_abacatepay",
            args=[condominio.slug, configuracao.pix_gateway_webhook_secret],
        )
    )

    return render(
        request,
        "core/configuracoes.html",
        {
            "condominio": condominio,
            "configuracao": configuracao,
            "form": form,
            "webhook_url": webhook_url,
            "notificacoes": {
                "emails_administracao": len(emails_administradores(condominio)),
                "email_configurado": bool(settings.EMAIL_HOST),
                "telegram_bot": bool(settings.TELEGRAM_BOT_TOKEN),
                "telegram_ativo": telegram_configurado(condominio),
                "agendador": bool(settings.TAREFAS_TOKEN),
            },
        },
    )


@login_required
@gestao_required
def identidade(request, slug):
    condominio = _condominio(request)
    form = IdentidadeForm(
        request.POST or None, request.FILES or None, instance=condominio
    )

    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except Exception as exc:
            logger.exception("Falha ao salvar identidade do condomínio")
            detalhe = f"{type(exc).__name__}: {exc}"[:240]
            messages.error(
                request,
                "Não foi possível salvar a imagem. "
                f"Detalhe técnico: {detalhe}",
            )
        else:
            messages.success(request, "Identidade do condomínio atualizada.")
            return redirect("identidade", slug=condominio.slug)

    return render(
        request,
        "core/identidade.html",
        {"condominio": condominio, "form": form},
    )


@login_required
@gestao_required
def locais(request, slug):
    condominio = _condominio(request)
    form = LocalForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        local = form.save(commit=False)
        local.condominio = condominio
        local.slug = _slug_unico(condominio, local.nome)
        local.save()
        messages.success(request, f"Espaço “{local.nome}” criado.")
        return redirect("locais", slug=condominio.slug)

    lista = Local.all_objects.filter(condominio=condominio).order_by("ordem", "nome")
    return render(
        request,
        "core/locais.html",
        {"condominio": condominio, "form": form, "locais": lista, "editando": None},
    )


@login_required
@gestao_required
def local_editar(request, slug, pk):
    condominio = _condominio(request)
    local = get_object_or_404(Local.all_objects, pk=pk, condominio=condominio)
    form = LocalForm(request.POST or None, request.FILES or None, instance=local)

    if request.method == "POST" and form.is_valid():
        local = form.save(commit=False)
        local.slug = _slug_unico(condominio, local.nome, ignorar=local)
        local.save()
        messages.success(request, f"Espaço “{local.nome}” atualizado.")
        return redirect("locais", slug=condominio.slug)

    lista = Local.all_objects.filter(condominio=condominio).order_by("ordem", "nome")
    return render(
        request,
        "core/locais.html",
        {"condominio": condominio, "form": form, "locais": lista, "editando": local},
    )


@login_required
@gestao_required
def local_alternar(request, slug, pk):
    condominio = _condominio(request)
    local = get_object_or_404(Local.all_objects, pk=pk, condominio=condominio)

    if request.method == "POST":
        local.ativo = not local.ativo
        local.save(update_fields=["ativo"])
        estado = "ativado" if local.ativo else "pausado"
        messages.success(request, f"Espaço “{local.nome}” {estado}.")

    return redirect("locais", slug=condominio.slug)


@login_required
@gestao_required
def unidades(request, slug):
    condominio = _condominio(request)
    form = UnidadeForm(request.POST or None, condominio=condominio)

    if request.method == "POST" and form.is_valid():
        unidade = form.save(commit=False)
        unidade.condominio = condominio
        unidade.save()
        messages.success(request, f"Unidade {unidade.rotulo} criada.")
        return redirect("unidades", slug=condominio.slug)

    return render(
        request,
        "core/unidades.html",
        {
            "condominio": condominio,
            "form": form,
            "unidades": condominio.unidades.filter(administrativa=False),
            "editando": None,
        },
    )


@login_required
@gestao_required
def unidade_editar(request, slug, pk):
    condominio = _condominio(request)
    unidade = get_object_or_404(condominio.unidades.filter(administrativa=False), pk=pk)
    form = UnidadeForm(request.POST or None, instance=unidade, condominio=condominio)

    if request.method == "POST" and form.is_valid():
        unidade = form.save()
        messages.success(request, f"Unidade {unidade.rotulo} atualizada.")
        return redirect("unidades", slug=condominio.slug)

    return render(
        request,
        "core/unidades.html",
        {
            "condominio": condominio,
            "form": form,
            "unidades": condominio.unidades.filter(administrativa=False),
            "editando": unidade,
            "vinculos": unidade.vinculos.select_related("usuario"),
        },
    )


@login_required
@gestao_required
def vinculo_remover(request, slug, pk):
    condominio = _condominio(request)
    if request.method != "POST":
        raise Http404

    vinculo = get_object_or_404(
        VinculoUnidade.objects.select_related("usuario", "unidade"),
        pk=pk,
        unidade__condominio=condominio,
        unidade__administrativa=False,
    )
    unidade = vinculo.unidade
    nome = vinculo.usuario.get_full_name() or vinculo.usuario.username
    vinculo.delete()
    messages.success(request, f"{nome} foi desvinculado da {unidade.rotulo}.")
    return redirect("unidade_editar", slug=condominio.slug, pk=unidade.pk)


@login_required
@gestao_required
def convites(request, slug):
    condominio = _condominio(request)
    form = ConviteForm(request.POST or None, condominio=condominio)

    if request.method == "POST" and form.is_valid():
        Convite.objects.create(
            condominio=condominio,
            unidade=form.cleaned_data["unidade"],
            papel=form.cleaned_data["papel"],
            criado_por=request.user,
        )
        messages.success(request, "Convite criado. Copie o link e envie ao morador.")
        return redirect("convites", slug=condominio.slug)

    lista = Convite.objects.filter(condominio=condominio).select_related("unidade", "usado_por")
    itens = [
        {
            "convite": convite,
            "link": request.build_absolute_uri(
                reverse(
                    "usar_convite",
                    kwargs={"slug": condominio.slug, "token": convite.token},
                )
            ),
        }
        for convite in lista
    ]
    for item in itens:
        item["mensagem"] = (
            f"Olá! Você foi convidado para a {item['convite'].unidade.rotulo} "
            f"do {condominio.nome}. Crie seu acesso aqui: {item['link']}"
        )

    return render(
        request,
        "core/convites.html",
        {"condominio": condominio, "form": form, "itens": itens},
    )


@login_required
@gestao_required
def convite_excluir(request, slug, pk):
    condominio = _condominio(request)
    if request.method != "POST":
        raise Http404

    convite = get_object_or_404(Convite, pk=pk, condominio=condominio)
    rotulo = convite.unidade.rotulo
    convite.delete()
    messages.success(request, f"Convite da {rotulo} excluído.")
    return redirect("convites", slug=condominio.slug)


@login_required
@gestao_required
def vinculo_redefinir_senha(request, slug, pk):
    condominio = _condominio(request)
    if request.method != "POST":
        raise Http404

    vinculo = get_object_or_404(
        VinculoUnidade.objects.select_related("usuario", "unidade"),
        pk=pk,
        unidade__condominio=condominio,
    )
    alvo = vinculo.usuario
    if pode_gerir(alvo, condominio) and not request.user.is_superuser:
        messages.error(
            request,
            "Não é possível redefinir a senha de outro administrador por aqui.",
        )
        return redirect(
            "unidade_editar", slug=condominio.slug, pk=vinculo.unidade.pk
        )

    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    senha = "".join(secrets.choice(alfabeto) for _ in range(10))
    alvo.set_password(senha)
    alvo.save(update_fields=["password"])

    texto = (
        f"Oi! Seu acesso ao {condominio.nome} foi atualizado.\n"
        f"Usuário: {alvo.username}\n"
        f"Senha temporária: {senha}\n"
        f"Entre em {request.build_absolute_uri(reverse('login'))} e troque a senha."
    )
    return render(
        request,
        "core/senha_temporaria.html",
        {
            "condominio": condominio,
            "alvo": alvo,
            "unidade": vinculo.unidade,
            "senha": senha,
            "mensagem": texto,
            "whatsapp": link_whatsapp(alvo.telefone, texto),
        },
    )


def usar_convite(request, slug, token):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = get_object_or_404(Condominio, slug=slug, ativo=True)
    if not condominio.acesso_liberado and not request.user.is_superuser:
        return render(
            request,
            "core/acesso_suspenso.html",
            {"condominio": condominio},
            status=403,
        )
    convite = get_object_or_404(Convite, condominio=condominio, token=token)

    if not convite.valido:
        return render(
            request,
            "core/convite.html",
            {"condominio": condominio, "convite": convite, "invalido": True},
        )

    if request.user.is_authenticated:
        usuario = request.user
        if request.method == "POST" and request.POST.get("acao") == "sair":
            logout(request)
            return redirect(
                "usar_convite",
                slug=condominio.slug,
                token=convite.token,
            )
        if VinculoUnidade.objects.filter(
            usuario=usuario, unidade=convite.unidade
        ).exists():
            return render(
                request,
                "core/convite.html",
                {"condominio": condominio, "convite": convite, "ja_vinculado": True},
            )

        form_telefone = None
        if not usuario.telefone:
            form_telefone = TelefoneForm(
                request.POST if request.method == "POST" else None
            )

        if request.method == "POST":
            acao = request.POST.get("acao")
            if acao == "usar":
                if form_telefone is not None and not form_telefone.is_valid():
                    return render(
                        request,
                        "core/convite.html",
                        {
                            "condominio": condominio,
                            "convite": convite,
                            "confirmar": True,
                            "form_telefone": form_telefone,
                        },
                    )
                if form_telefone is not None:
                    usuario.telefone = form_telefone.cleaned_data["telefone"]
                    usuario.save(update_fields=["telefone"])
                VinculoUnidade.objects.get_or_create(
                    usuario=usuario,
                    unidade=convite.unidade,
                    papel=convite.papel,
                    defaults={"ativo": True},
                )
                convite.usado_em = timezone.now()
                convite.usado_por = usuario
                convite.save(update_fields=["usado_em", "usado_por"])
                nome = usuario.first_name or usuario.username
                messages.success(
                    request,
                    f"Pronto, {nome}! Seu vínculo com o {condominio.nome} está ativo.",
                )
                return redirect("agenda", slug=condominio.slug)

        return render(
            request,
            "core/convite.html",
            {
                "condominio": condominio,
                "convite": convite,
                "confirmar": True,
                "form_telefone": form_telefone,
            },
        )

    form = CadastroConviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario = Usuario.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["senha"],
                first_name=form.cleaned_data["nome"],
                telefone=form.cleaned_data["telefone"],
            )
            VinculoUnidade.objects.create(
                usuario=usuario,
                unidade=convite.unidade,
                papel=convite.papel,
            )
            convite.usado_em = timezone.now()
            convite.usado_por = usuario
            convite.save(update_fields=["usado_em", "usado_por"])
        login(request, usuario)
        messages.success(
            request,
            f"Cadastro concluído, {usuario.first_name}! Você agora faz parte do "
            f"{condominio.nome}.",
        )
        return redirect("agenda", slug=condominio.slug)

    return render(
        request,
        "core/convite.html",
        {"condominio": condominio, "convite": convite, "form": form},
    )


def plataforma_entrar(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("plataforma")

    form = EntrarForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        if not usuario.is_superuser:
            form.add_error(
                None,
                "Esta conta é de morador ou síndico. Use a entrada do condomínio.",
            )
        else:
            login(request, usuario)
            return redirect("plataforma")

    return render(request, "core/plataforma_login.html", {"form": form})


def _plataforma_required(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            return redirect("plataforma_entrar")
        return view(request, *args, **kwargs)

    return _wrapped


@_plataforma_required
def plataforma_painel(request):
    form = NovoCondominioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        condominio = form.save()
        messages.success(request, f"Condomínio “{condominio.nome}” criado.")
        return redirect("plataforma")

    condominios = Condominio.objects.annotate(
        total_unidades=Count("unidades", filter=Q(unidades__administrativa=False), distinct=True),
        total_locais=Count("locais", distinct=True),
        total_reservas=Count("reservas", distinct=True),
    ).order_by("nome")
    for condominio in condominios:
        condominio.plano_sugerido = Plano.para_quantidade(
            condominio.quantidade_unidades or condominio.total_unidades
        )

    pagamentos_pendentes = PagamentoPlano.objects.filter(
        status=PagamentoPlano.Status.PENDENTE
    ).select_related("condominio", "plano")

    return render(
        request,
        "core/plataforma.html",
        {
            "form": form,
            "condominios": condominios,
            "pagamentos_pendentes": pagamentos_pendentes,
            "dias_assinatura": settings.ASSINATURA_DIAS,
        },
    )


@_plataforma_required
def plataforma_armazenamento(request):
    erro = None
    enviado = None

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            erro = "Escolha um arquivo para testar."
        else:
            try:
                publico = storages["default"]
                nome = publico.save(f"testes/{uuid4().hex}-{arquivo.name}", arquivo)
                enviado = publico.url(nome)
            except Exception as exc:
                logger.exception("Teste de armazenamento falhou")
                erro = f"{type(exc).__name__}: {exc}"

    publico = storages["default"]
    privado = armazenamento_privado()

    def resumo(storage):
        try:
            bucket = getattr(storage, "bucket_name", None)
        except Exception:
            bucket = None
        return {
            "backend": f"{type(storage).__module__}.{type(storage).__name__}",
            "bucket": bucket,
        }

    try:
        exemplo_url = publico.url("testes/exemplo.png")
    except Exception as exc:
        exemplo_url = f"{type(exc).__name__}: {exc}"

    if settings.STORAGE_S3_ATIVO:
        modo = "R2/S3"
    elif getattr(settings, "CLOUDINARY_CLOUD_NAME", ""):
        modo = "Cloudinary"
    else:
        modo = "disco local"

    return render(
        request,
        "core/plataforma_armazenamento.html",
        {
            "publico": resumo(publico),
            "privado": resumo(privado),
            "endpoint": getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            "dominio": getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None),
            "exemplo_url": exemplo_url,
            "modo": modo,
            "debug": settings.DEBUG,
            "usando_cloudinary": bool(getattr(settings, "CLOUDINARY_CLOUD_NAME", "")),
            "enviado": enviado,
            "erro": erro,
        },
    )


@_plataforma_required
def plataforma_pagamento_confirmar(request, pk):
    if request.method != "POST":
        raise Http404

    pagamento = get_object_or_404(
        PagamentoPlano.objects.select_related("condominio", "plano"), pk=pk
    )
    acao = request.POST.get("acao")
    if acao not in {"confirmar", "recusar"}:
        raise Http404

    pagamento.analisado_em = timezone.now()
    pagamento.analisado_por = request.user
    pagamento.observacao = (request.POST.get("observacao") or "").strip()[:200]
    if acao == "confirmar":
        pagamento.status = PagamentoPlano.Status.CONFIRMADO
        condominio = pagamento.condominio
        base = timezone.now()
        if condominio.trial_ate and condominio.trial_ate > base:
            base = condominio.trial_ate
        if (
            condominio.assinatura_valida_ate
            and condominio.assinatura_valida_ate > base
        ):
            base = condominio.assinatura_valida_ate
        condominio.assinatura_valida_ate = base + timedelta(
            days=settings.ASSINATURA_DIAS
        )
        condominio.plano = pagamento.plano
        condominio.isento_assinatura = False
        condominio.save(
            update_fields=[
                "assinatura_valida_ate",
                "plano",
                "isento_assinatura",
            ]
        )
        messages.success(
            request,
            f"Plano de {condominio.nome} liberado até "
            f"{timezone.localtime(condominio.assinatura_valida_ate):%d/%m/%Y}.",
        )
    else:
        pagamento.status = PagamentoPlano.Status.RECUSADO
        messages.info(
            request,
            f"Comprovante de {pagamento.condominio.nome} recusado.",
        )
    pagamento.save(
        update_fields=["status", "analisado_em", "analisado_por", "observacao"]
    )
    return redirect("plataforma")


@_plataforma_required
def plataforma_pagamento_comprovante(request, pk):
    pagamento = get_object_or_404(PagamentoPlano, pk=pk)
    if not pagamento.comprovante:
        raise Http404("Comprovante não encontrado.")
    arquivo = pagamento.comprovante.open("rb")
    return FileResponse(
        arquivo,
        as_attachment=False,
        filename=Path(pagamento.comprovante.name).name,
    )


@_plataforma_required
def plataforma_liberar(request, pk):
    if request.method != "POST":
        raise Http404

    condominio = get_object_or_404(Condominio, pk=pk)
    base = timezone.now()
    if condominio.trial_ate and condominio.trial_ate > base:
        base = condominio.trial_ate
    if condominio.assinatura_valida_ate and condominio.assinatura_valida_ate > base:
        base = condominio.assinatura_valida_ate
    condominio.assinatura_valida_ate = base + timedelta(
        days=settings.ASSINATURA_DIAS
    )
    condominio.isento_assinatura = False
    condominio.save(update_fields=["assinatura_valida_ate", "isento_assinatura"])
    messages.success(
        request,
        f"{condominio.nome} liberado até "
        f"{timezone.localtime(condominio.assinatura_valida_ate):%d/%m/%Y}.",
    )
    return redirect("plataforma")
