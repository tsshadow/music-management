<script lang="ts">
  export let label: string;
  export let value: string | number;
</script>

<div class="card">
  <span class="label">{label}</span>
  <span class="value">{value}</span>
</div>

<style>
  .card {
    background: rgba(0, 0, 0, 0.4);
    border-radius: 1.5rem;
    padding: 2rem 3rem;
    min-width: 280px;
    text-align: center;
    color: var(--text-color);
    box-shadow: 0 20px 45px rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .label {
    display: block;
    text-transform: uppercase;
    letter-spacing: 0.25em;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.6);
    margin-bottom: 0.5rem;
  }

  .value {
    font-size: clamp(2rem, 5vw, 3.5rem);
    font-weight: 700;
  }
</style>
