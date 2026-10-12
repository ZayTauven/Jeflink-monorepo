"use client";

import { useEffect, useRef } from "react";

/**
 * « Main show » de l'accueil : une sculpture de disques blancs empilés qui ondulent (l'esprit
 * de la boule Crafto), posée sur la lueur orange du concept de logo, avec l'étincelle Jeflink
 * en orbite. Canvas 2D, aucune dépendance. Une seule image fixe si l'utilisateur préfère moins
 * d'animations ; pause quand le hero sort de l'écran.
 */
export function HeroShow({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let visible = true;
    let w = 0;
    let h = 0;
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const SLICES = 38;
    const STEPS = 72;
    const TILT = 0.3; // vue légèrement plongeante

    function sparkle(x: number, y: number, s: number, rot: number, alpha: number) {
      ctx!.save();
      ctx!.translate(x, y);
      ctx!.rotate(rot);
      ctx!.globalAlpha = alpha;
      ctx!.beginPath();
      ctx!.moveTo(0, -s);
      ctx!.quadraticCurveTo(s * 0.12, -s * 0.12, s, 0);
      ctx!.quadraticCurveTo(s * 0.12, s * 0.12, 0, s);
      ctx!.quadraticCurveTo(-s * 0.12, s * 0.12, -s, 0);
      ctx!.quadraticCurveTo(-s * 0.12, -s * 0.12, 0, -s);
      ctx!.closePath();
      const g = ctx!.createLinearGradient(-s, -s, s, s);
      g.addColorStop(0, "#ffb23e");
      g.addColorStop(1, "#f55608");
      ctx!.fillStyle = g;
      ctx!.shadowColor = "rgba(245, 86, 8, 0.55)";
      ctx!.shadowBlur = s * 1.2;
      ctx!.fill();
      ctx!.restore();
    }

    function frame(t: number) {
      const time = t / 1000;
      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;
      ctx!.clearRect(0, 0, w, h);

      const R = Math.min(w, h) * 0.34;
      const cx = w / 2 + pointer.x * 18;
      const cy = h / 2 + pointer.y * 12;

      // Lueur orange sous la sculpture (le flou du concept de logo).
      const breathe = 1 + Math.sin(time * 0.8) * 0.06;
      const glow = ctx!.createRadialGradient(
        cx + R * 0.45,
        cy + R * 0.75,
        0,
        cx + R * 0.45,
        cy + R * 0.75,
        R * 1.15 * breathe,
      );
      glow.addColorStop(0, "rgba(245, 86, 8, 0.42)");
      glow.addColorStop(0.45, "rgba(245, 120, 40, 0.16)");
      glow.addColorStop(1, "rgba(245, 120, 40, 0)");
      ctx!.fillStyle = glow;
      ctx!.fillRect(0, 0, w, h);

      // Orbite de l'étincelle : moitié arrière dessinée avant la sculpture, moitié avant après.
      const orbitA = time * 0.55;
      const ox = cx + Math.cos(orbitA) * R * 1.18;
      const oy = cy + Math.sin(orbitA) * R * 0.36 + R * 0.05;
      const front = Math.sin(orbitA) > 0;
      const sparkSize = R * (front ? 0.13 : 0.09);
      if (!front) sparkle(ox, oy, sparkSize, time * 0.8, 0.5);

      // Ombre portée.
      const shadow = ctx!.createRadialGradient(cx, cy + R * 1.08, 0, cx, cy + R * 1.08, R * 0.95);
      shadow.addColorStop(0, "rgba(60, 40, 20, 0.18)");
      shadow.addColorStop(1, "rgba(60, 40, 20, 0)");
      ctx!.fillStyle = shadow;
      ctx!.beginPath();
      ctx!.ellipse(cx, cy + R * 1.08, R * 0.95, R * 0.2, 0, 0, Math.PI * 2);
      ctx!.fill();

      // Disques empilés, du haut vers le bas : chaque disque inférieur recouvre l'avant du
      // précédent, ce qui dessine des rainures sur une sphère. Le bord de chaque disque ondule
      // (trois vagues qui tournent lentement) : la sculpture semble pivoter sur elle-même.
      for (let i = 0; i < SLICES; i++) {
        const v = -1 + (2 * (i + 0.5)) / SLICES; // -1 (haut) → 1 (bas)
        const base = Math.sqrt(Math.max(0, 1 - v * v));
        const r = R * base;
        if (r < 2) continue;
        const sy = cy + v * R * 0.94;
        const sx = cx + pointer.x * v * 8;
        const phase = time * 0.45 + i * 0.38;
        const amp = 0.045 * Math.sin(time * 0.9 + i * 0.3);

        ctx!.beginPath();
        for (let k = 0; k <= STEPS; k++) {
          const a = (k / STEPS) * Math.PI * 2;
          const rr = r * (1 + amp * Math.sin(3 * a + phase));
          const px = sx + Math.cos(a) * rr;
          const py = sy + Math.sin(a) * rr * TILT;
          if (k === 0) ctx!.moveTo(px, py);
          else ctx!.lineTo(px, py);
        }
        ctx!.closePath();
        const fill = ctx!.createLinearGradient(sx - r, sy - r * TILT, sx + r, sy + r * TILT);
        fill.addColorStop(0, "#ffffff");
        fill.addColorStop(0.5, "#f4f2ed");
        fill.addColorStop(1, "#d8d3c9");
        ctx!.fillStyle = fill;
        ctx!.shadowColor = "rgba(40, 30, 20, 0.14)";
        ctx!.shadowBlur = 8;
        ctx!.shadowOffsetY = 3;
        ctx!.fill();
        ctx!.shadowColor = "transparent";
        ctx!.lineWidth = 1;
        ctx!.strokeStyle = "rgba(255, 255, 255, 0.95)";
        ctx!.stroke();
      }

      if (front) sparkle(ox, oy, sparkSize, time * 0.8, 1);

      if (!reduced && visible) raf = requestAnimationFrame(frame);
    }

    resize();
    const onResize = () => {
      resize();
      if (reduced) frame(4000);
    };
    const onMove = (e: PointerEvent) => {
      pointer.tx = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.ty = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    const io = new IntersectionObserver(([entry]) => {
      const wasVisible = visible;
      visible = entry.isIntersecting;
      if (visible && !wasVisible && !reduced) raf = requestAnimationFrame(frame);
    });
    io.observe(canvas);
    window.addEventListener("resize", onResize);
    if (!reduced) window.addEventListener("pointermove", onMove);
    raf = requestAnimationFrame(reduced ? () => frame(4000) : frame);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
