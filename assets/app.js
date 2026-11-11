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
