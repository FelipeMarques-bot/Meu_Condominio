import logging
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.reservas.models import Local
from apps.usuarios.forms import CadastroConviteForm, ConviteForm
from apps.usuarios.models import Convite, Unidade, Usuario, VinculoUnidade

from .forms import (
    CondominioDoUsuarioForm,
    ConfiguracaoForm,
    EntrarForm,
    IdentidadeForm,
    LocalForm,
    NovoCondominioForm,
    OnboardingForm,
    UnidadeForm,
    slug_condominio_unico,
)
from .models import Condominio, Plano
from .permissoes import gestao_required

logger = logging.getLogger(__name__)


def _condominio(request):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = None
    return condominio


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


def criar_condominio(request):
    """Onboarding: condomínio, primeira unidade e conta (ou vínculo) de síndico."""
    if request.user.is_authenticated:
        form = CondominioDoUsuarioForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            dados = form.cleaned_data
            with transaction.atomic():
                condominio = Condominio.objects.create(
                    nome=dados["nome"],
                    slug=slug_condominio_unico(dados["nome"], dados["slug"]),
                    plano=Plano.para_quantidade(1),
                    trial_ate=timezone.now() + timedelta(days=14),
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
                f"{condominio.nome} criado! Você é síndico e tem 14 dias de teste.",
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
        with transaction.atomic():
            condominio = Condominio.objects.create(
                nome=dados["condominio"],
                slug=slug_condominio_unico(dados["condominio"], dados["slug"]),
                plano=Plano.para_quantidade(1),
                trial_ate=timezone.now() + timedelta(days=14),
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
            f"{condominio.nome} está no ar! Você tem 14 dias de teste e já entra "
            "como síndico.",
        )
        return redirect("gestao", slug=condominio.slug)

    return render(request, "core/criar_condominio.html", {"form": form})


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
        vinculo = (
            usuario.vinculos.filter(ativo=True)
            .select_related("unidade__condominio")
            .order_by("pk")
            .first()
        )
        if vinculo is not None:
            return reverse("agenda", args=[vinculo.unidade.condominio.slug])
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
    return render(
        request,
        "core/minha_conta.html",
        {"condominio": condominio, "vinculos": vinculos},
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
        except Exception:
            logger.exception("Falha ao salvar identidade do condomínio")
            messages.error(
                request,
                "Não foi possível salvar a imagem. Confira o armazenamento "
                "(R2/Cloudinary) e tente novamente.",
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
        },
    )


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

    return render(
        request,
        "core/convites.html",
        {"condominio": condominio, "form": form, "itens": itens},
    )


def usar_convite(request, slug, token):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = get_object_or_404(Condominio, slug=slug, ativo=True)
    convite = get_object_or_404(Convite, condominio=condominio, token=token)

    if not convite.valido:
        return render(
            request,
            "core/convite.html",
            {"condominio": condominio, "convite": convite, "invalido": True},
        )

    if request.user.is_authenticated:
        VinculoUnidade.objects.get_or_create(
            usuario=request.user,
            unidade=convite.unidade,
            papel=convite.papel,
            defaults={"ativo": True},
        )
        convite.usado_em = timezone.now()
        convite.usado_por = request.user
        convite.save(update_fields=["usado_em", "usado_por"])
        nome = request.user.first_name or request.user.username
        messages.success(
            request,
            f"Pronto, {nome}! Seu vínculo com o {condominio.nome} está ativo.",
        )
        return redirect("agenda", slug=condominio.slug)

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

    return render(
        request,
        "core/plataforma.html",
        {"form": form, "condominios": condominios},
    )
