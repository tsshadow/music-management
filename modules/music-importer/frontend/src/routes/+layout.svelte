<script lang="ts">
        import '../app.css';
        import MatrixBackground from '$lib/MatrixBackground.svelte';

        let { children } = $props();
</script>

<MatrixBackground />
{@render children()}
