import "./app.css";
import htmx from "htmx.org";
import Alpine from "alpinejs";
import { animate, stagger } from "animejs";

window.htmx = htmx;
window.Alpine = Alpine;
Alpine.start();

const prefereMenosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const alvos = document.querySelectorAll(".reveal");

if (!prefereMenosMovimento && alvos.length) {
  animate(alvos, {
    opacity: [0, 1],
    translateY: [18, 0],
    duration: 780,
    delay: stagger(70),
    ease: "out(4)",
  });
}

const podeUsarTresD = window.matchMedia("(min-width: 1024px)").matches;
const canvasHero = document.querySelector("[data-hero-canvas]");

if (podeUsarTresD && !prefereMenosMovimento && canvasHero) {
  import("./hero3d.js")
    .then(({ montarHero }) => montarHero(canvasHero))
    .catch(() => {
      canvasHero.remove();
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
