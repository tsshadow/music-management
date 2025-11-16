<script lang="ts">
  export let title: string;
</script>

<header class="hero">
  <div class="backdrop"></div>
  <div class="content">
    <h1>{title}</h1>
    <p>Track your listening history and insights.</p>
  </div>
</header>

<style>
  .hero {
    position: relative;
    padding: 4rem 2rem 3rem;
    display: flex;
    justify-content: center;
    align-items: center;
    color: var(--text-color);
    overflow: hidden;
  }

  .backdrop {
    position: absolute;
    inset: 0;
    background: var(--header-gradient);
    filter: blur(60px);
    opacity: 0.6;
    z-index: 0;
  }

  .content {
    position: relative;
    z-index: 1;
    text-align: center;
    max-width: 720px;
  }

  h1 {
    font-size: clamp(2.5rem, 4vw, 4rem);
    margin-bottom: 0.75rem;
  }

  p {
    margin: 0;
    font-size: 1.1rem;
    color: rgba(255, 255, 255, 0.75);
  }
</style>
