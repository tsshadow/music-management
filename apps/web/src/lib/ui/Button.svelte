<script lang="ts">
  /**
   * Button is a themed action trigger supporting primary and subtle variants.
   */
  export let variant: 'primary' | 'ghost' = 'primary';
  export let disabled = false;
  export let type: 'button' | 'submit' = 'button';
</script>

<button class={variant} {disabled} {type}>
  <slot />
</button>

<style>
  button {
    border: none;
    border-radius: calc(var(--radius-base) / 1.5);
    cursor: pointer;
    font-weight: 600;
    padding: 0.75rem 1.5rem;
    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.2s ease;
  }

  button.primary {
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-accent));
    color: #0f172a;
    box-shadow: 0 10px 30px rgba(14, 165, 233, 0.35);
  }

  button.primary:hover {
    transform: translateY(-1px);
  }

  button.ghost {
    background: transparent;
    border: 1px solid rgba(148, 163, 184, 0.4);
    color: var(--color-text);
  }

  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    box-shadow: none;
  }
</style>
