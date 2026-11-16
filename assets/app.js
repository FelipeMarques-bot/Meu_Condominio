import "./app.css";
import htmx from "htmx.org";
import Alpine from "alpinejs";

window.htmx = htmx;
window.Alpine = Alpine;
Alpine.start();

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
