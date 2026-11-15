import * as THREE from "three";

export function montarHero(container) {
  let renderer;

  try {
    renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "low-power",
    });
  } catch {
    container.remove();
    return;
  }

  const cena = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 7.2);

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);
  renderer.domElement.style.width = "100%";
  renderer.domElement.style.height = "100%";
  renderer.domElement.style.display = "block";

  const grupo = new THREE.Group();
  grupo.position.set(1.15, 0.1, 0);
  cena.add(grupo);

  const materialLinha = new THREE.LineBasicMaterial({
    color: 0x0e4a55,
    transparent: true,
    opacity: 0.26,
  });

  const aneis = [];
  [1.35, 1.85, 2.4].forEach((raio, indice) => {
    const geometria = new THREE.RingGeometry(raio, raio + 0.004, 220);
    const anel = new THREE.LineLoop(geometria, materialLinha);
    anel.rotation.x = Math.PI / 2.35 + indice * 0.1;
    anel.rotation.y = indice * 0.45;
    grupo.add(anel);
    aneis.push(anel);
  });

  const quantidade = 160;
  const posicoes = new Float32Array(quantidade * 3);
  for (let i = 0; i < quantidade; i += 1) {
    const angulo = Math.random() * Math.PI * 2;
    const raio = 1.1 + Math.random() * 1.55;
    posicoes[i * 3] = Math.cos(angulo) * raio;
    posicoes[i * 3 + 1] = (Math.random() - 0.5) * 2.4;
    posicoes[i * 3 + 2] = Math.sin(angulo) * raio;
  }

  const geometriaPontos = new THREE.BufferGeometry();
  geometriaPontos.setAttribute("position", new THREE.BufferAttribute(posicoes, 3));

  const pontos = new THREE.Points(
    geometriaPontos,
    new THREE.PointsMaterial({
      color: 0xa9553a,
      size: 0.028,
      transparent: true,
      opacity: 0.55,
      sizeAttenuation: true,
    }),
  );
  grupo.add(pontos);

  const ponteiro = { x: 0, y: 0 };
  const alvo = { x: 0, y: 0 };

  function aoMover(evento) {
    alvo.x = (evento.clientX / window.innerWidth - 0.5) * 2;
    alvo.y = (evento.clientY / window.innerHeight - 0.5) * 2;
  }

  window.addEventListener("pointermove", aoMover, { passive: true });

  const secao = container.closest("section") ?? container.parentElement;
  const permiteMovimento = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let alvoProgresso = 0;
  let progresso = 0;
  let quadroScroll = 0;

  function medirProgresso() {
    quadroScroll = 0;
    if (!permiteMovimento || !secao) return;
    const caixa = secao.getBoundingClientRect();
    const percorrido = -caixa.top;
    alvoProgresso = Math.min(Math.max(percorrido / Math.max(caixa.height, 1), 0), 1);
  }

  function aoRolar() {
    if (quadroScroll) return;
    quadroScroll = requestAnimationFrame(medirProgresso);
  }

  if (permiteMovimento && secao) {
    medirProgresso();
    window.addEventListener("scroll", aoRolar, { passive: true });
    window.addEventListener("resize", aoRolar);
  }

  function ajustarTamanho() {
    const { width, height } = container.getBoundingClientRect();
    if (!width || !height) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  }

  const observador = new ResizeObserver(ajustarTamanho);
  observador.observe(container);
  ajustarTamanho();

  const relogio = new THREE.Clock();
  let tempo = 0;
  let animacao = 0;
  let ativo = true;
  let visivel = true;

  function animar() {
    if (!ativo || !visivel) return;
    animacao = requestAnimationFrame(animar);

    tempo += Math.min(relogio.getDelta(), 0.1);
    ponteiro.x += (alvo.x - ponteiro.x) * 0.045;
    ponteiro.y += (alvo.y - ponteiro.y) * 0.045;
    progresso += (alvoProgresso - progresso) * 0.075;

    const p = progresso;

    camera.position.set(
      -p * 0.55 + ponteiro.x * 0.16,
      p * 0.85 - ponteiro.y * 0.1,
      7.2 - p * 0.85,
    );
    camera.lookAt(0.25, 0, 0);

    grupo.position.set(1.15 - p * 0.95, 0.1 - p * 0.7, p * 0.45);
    grupo.rotation.y = tempo * 0.06 + ponteiro.x * 0.12 + p * 1.05;
    grupo.rotation.x = ponteiro.y * 0.08 + p * 0.4;
    grupo.rotation.z = p * -0.12;
    grupo.scale.setScalar(1 + p * 0.08);

    materialLinha.opacity = 0.26 - p * 0.12;
    pontos.material.opacity = 0.55 - p * 0.22;

    aneis.forEach((anel, indice) => {
      anel.rotation.z = tempo * (0.03 + indice * 0.012) + p * (0.4 + indice * 0.25);
    });

    pontos.rotation.y = -tempo * 0.03 - p * 0.5;

    renderer.render(cena, camera);
  }

  const observadorVisivel = new IntersectionObserver(
    ([entrada]) => {
      visivel = entrada.isIntersecting;
      if (visivel && ativo) {
        cancelAnimationFrame(animacao);
        animar();
      }
    },
    { threshold: 0 },
  );
  observadorVisivel.observe(container);

  animar();

  function aoTrocarVisibilidade() {
    ativo = !document.hidden;
    if (ativo && visivel) {
      cancelAnimationFrame(animacao);
      animar();
    } else {
      cancelAnimationFrame(animacao);
    }
  }

  document.addEventListener("visibilitychange", aoTrocarVisibilidade);

  return () => {
    ativo = false;
    cancelAnimationFrame(animacao);
    cancelAnimationFrame(quadroScroll);
    observador.disconnect();
    observadorVisivel.disconnect();
    window.removeEventListener("pointermove", aoMover);
    window.removeEventListener("scroll", aoRolar);
    window.removeEventListener("resize", aoRolar);
    document.removeEventListener("visibilitychange", aoTrocarVisibilidade);
    renderer.dispose();
    container.remove();
  };
}
