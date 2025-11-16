<script>
import { onMount } from 'svelte';
let canvas;

onMount(() => {
  const ctx = canvas.getContext('2d');
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const fontSize = 16;
  const columns = Math.floor(canvas.width / fontSize);
  const drops = Array(columns).fill(0);
  const letters = '0123456789ABCDEF';

  function draw() {
    ctx.fillStyle = 'rgba(0,0,0,0.05)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#0f0';
    ctx.font = fontSize + 'px monospace';
    for (let i = 0; i < drops.length; i++) {
      const text = letters[Math.floor(Math.random() * letters.length)];
      ctx.fillText(text, i * fontSize, drops[i] * fontSize);
      if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
        drops[i] = 0;
      }
      drops[i]++;
    }
    requestAnimationFrame(draw);
  }
  draw();
});
</script>

<canvas bind:this={canvas} class="fixed inset-0 -z-10 opacity-20"></canvas>
