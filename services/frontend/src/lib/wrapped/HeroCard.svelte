<script>
  /** The title card of a tab: the period, the listen count and what they add up to. */
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null } = $props();
</script>

<CardFrame {face} {tint} {onshare} hero />
