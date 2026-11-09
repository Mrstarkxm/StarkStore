
document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const toggle = document.getElementById("themeToggle");
  const savedTheme = localStorage.getItem("stark-theme");
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  const initialTheme = savedTheme || "light";

  function setTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem("stark-theme", theme);
    if (toggle) {
      const icon = toggle.querySelector(".theme-icon");
      const label = toggle.querySelector(".theme-label");
      if (icon) icon.textContent = theme === "dark" ? "☀" : "☾";
      if (label) label.textContent = theme === "dark" ? "Light" : "Dark";
      toggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    }
  }
  setTheme(initialTheme);
  if (toggle) toggle.addEventListener("click", () => setTheme(root.dataset.theme === "dark" ? "light" : "dark"));

  document.querySelectorAll(".flash").forEach(el => setTimeout(() => {
    el.style.opacity = "0"; el.style.transform = "translateY(-8px)";
  }, 4000));

  const revealItems = document.querySelectorAll(".reveal, .product-card, .stat-card, .admin-panel");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    }), {threshold: 0.08});
    revealItems.forEach(el => observer.observe(el));
  } else revealItems.forEach(el => el.classList.add("is-visible"));

  // Pointer-responsive 3D product cards (disabled for touch/reduced-motion devices).
  const finePointer = window.matchMedia("(pointer:fine)").matches;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (finePointer && !reduceMotion) {
    document.querySelectorAll(".product-card").forEach(card => {
      card.addEventListener("pointermove", e => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - .5;
        const y = (e.clientY - r.top) / r.height - .5;
        card.style.setProperty("--rx", `${-y * 5}deg`);
        card.style.setProperty("--ry", `${x * 7}deg`);
      });
      card.addEventListener("pointerleave", () => {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    });

    const scene = document.getElementById("heroScene");
    if (scene) scene.addEventListener("pointermove", e => {
      const r = scene.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5;
      const y = (e.clientY - r.top) / r.height - .5;
      scene.style.setProperty("--scene-x", `${x * 10}deg`);
      scene.style.setProperty("--scene-y", `${-y * 8}deg`);
    });
    if (scene) scene.addEventListener("pointerleave", () => {
      scene.style.setProperty("--scene-x", "0deg");
      scene.style.setProperty("--scene-y", "0deg");
    });
  }
});
