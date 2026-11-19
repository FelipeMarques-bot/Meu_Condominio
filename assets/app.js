import "./app.css";
import htmx from "htmx.org";
import Alpine from "alpinejs";

window.htmx = htmx;
window.Alpine = Alpine;

Alpine.data("calendarioDias", () => ({
  dados: {},
  aberto: null,

  init() {
    const fonte = document.getElementById("calendario-dados");
    if (!fonte) return;
    try {
      this.dados = JSON.parse(fonte.textContent) || {};
    } catch {
      this.dados = {};
    }
  },

  abrir(chave) {
    if (!chave) return;
    const info = this.dados[chave];
    if (info) {
      this.aberto = info;
    } else {
      const [ano, mes, dia] = chave.split("-").map(Number);
      const data = new Date(ano, mes - 1, dia);
      this.aberto = {
        rotulo: new Intl.DateTimeFormat("pt-BR", {
          weekday: "long",
          day: "2-digit",
          month: "long",
        })
          .format(data)
          .replace(/^./, (letra) => letra.toUpperCase()),
        eventos: [],
      };
    }
    document.documentElement.classList.add("nav-aberto");
    this.$nextTick(() => this.$refs.painel?.focus());
  },

  fechar() {
    this.aberto = null;
    document.documentElement.classList.remove("nav-aberto");
  },
}));

const prefereMenosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const revelaveis = document.querySelectorAll(".reveal");

if (!prefereMenosMovimento && revelaveis.length) {
  document.documentElement.classList.add("reveal-ativo");

  const observador = new IntersectionObserver(
    (entradas) => {
      entradas.forEach((entrada) => {
        if (!entrada.isIntersecting) return;
        entrada.target.classList.add("revelado");
        observador.unobserve(entrada.target);
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
  );

  revelaveis.forEach((elemento) => {
    const irmaos = Array.from(
      elemento.parentElement?.querySelectorAll(":scope > .reveal") ?? [],
    );
    const posicao = Math.max(irmaos.indexOf(elemento), 0);
    elemento.style.transitionDelay = `${Math.min(posicao, 7) * 70}ms`;
    observador.observe(elemento);
  });
}

const canvasesHero = document.querySelectorAll("[data-hero-canvas]");

if (!prefereMenosMovimento && canvasesHero.length) {
  import("./hero3d.js")
    .then(({ montarHero }) => {
      canvasesHero.forEach((canvas) => montarHero(canvas));
    })
    .catch(() => {
      canvasesHero.forEach((canvas) => canvas.remove());
    });
}

const elementosTilt = document.querySelectorAll("[data-tilt-scroll]");

if (!prefereMenosMovimento && elementosTilt.length) {
  let quadro = 0;

  const atualizarTilt = () => {
    quadro = 0;
    const alturaJanela = window.innerHeight;

    elementosTilt.forEach((elemento) => {
      const caixa = elemento.getBoundingClientRect();
      const progresso = Math.min(
        Math.max((alturaJanela - caixa.top) / (alturaJanela + caixa.height), 0),
        1,
      );
      const inclinacao = (0.5 - progresso) * 2;

      elemento.style.transform = `perspective(1400px) rotateX(${(inclinacao * 6).toFixed(2)}deg) rotateY(${(inclinacao * -5).toFixed(2)}deg) translateZ(${(progresso * 24).toFixed(1)}px)`;
    });
  };

  const agendarTilt = () => {
    if (quadro) return;
    quadro = requestAnimationFrame(atualizarTilt);
  };

  atualizarTilt();
  window.addEventListener("scroll", agendarTilt, { passive: true });
  window.addEventListener("resize", agendarTilt);
}

const modoAplicativo =
  window.matchMedia("(display-mode: standalone)").matches ||
  window.matchMedia("(display-mode: fullscreen)").matches ||
  window.navigator.standalone === true;

const ehIOS =
  /iphone|ipad|ipod/i.test(window.navigator.userAgent) ||
  (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);

let conviteInstalacao = null;

const blocosInstalacao = () => document.querySelectorAll("[data-instalar-bloco]");

const atualizarBlocosInstalacao = () => {
  blocosInstalacao().forEach((bloco) => {
    bloco.hidden = modoAplicativo;
    const botao = bloco.querySelector("[data-instalar-pwa]");
    const dica = bloco.querySelector("[data-dica-ios]");
    if (botao) {
      botao.hidden = false;
      botao.textContent = conviteInstalacao ? "Instalar aplicativo" : "Como instalar no celular";
    }
    if (dica) dica.hidden = !ehIOS || modoAplicativo;
  });
};

window.addEventListener("beforeinstallprompt", (evento) => {
  evento.preventDefault();
  conviteInstalacao = evento;
  atualizarBlocosInstalacao();
});

window.addEventListener("appinstalled", () => {
  conviteInstalacao = null;
  atualizarBlocosInstalacao();
});

document.addEventListener("click", async (evento) => {
  const botao = evento.target.closest("[data-instalar-pwa]");
  if (!botao) return;

  if (conviteInstalacao) {
    conviteInstalacao.prompt();
    const escolha = await conviteInstalacao.userChoice;
    if (escolha?.outcome === "accepted") {
      conviteInstalacao = null;
      atualizarBlocosInstalacao();
    }
    return;
  }

  const bloco = botao.closest("[data-instalar-bloco]");
  const dica = bloco?.querySelector("[data-dica-ios]");
  if (dica) {
    dica.hidden = !dica.hidden;
    if (!dica.hidden) dica.focus?.();
  }
});

document.querySelectorAll('input[type="password"]').forEach((campo) => {
  const pai = campo.parentElement;
  if (!pai || pai.querySelector(":scope > .olho-senha")) return;

  pai.classList.add("campo-senha");
  const botao = document.createElement("button");
  botao.type = "button";
  botao.className = "olho-senha";
  botao.textContent = "Mostrar";
  botao.setAttribute("aria-label", "Mostrar senha");
  botao.setAttribute("aria-pressed", "false");

  botao.addEventListener("click", () => {
    const visivel = campo.type === "text";
    campo.type = visivel ? "password" : "text";
    botao.textContent = visivel ? "Mostrar" : "Ocultar";
    botao.setAttribute("aria-pressed", String(!visivel));
  });

  pai.appendChild(botao);
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

atualizarBlocosInstalacao();
Alpine.start();

