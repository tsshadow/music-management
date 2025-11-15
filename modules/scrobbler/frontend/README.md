# Frontend style guide

This frontend uses Tailwind CSS for layout and theming so future modules (for example the
rating or rule editor) can share the same look and feel.

## Tailwind theme

The Tailwind configuration lives in `tailwind.config.cjs` and exposes the design tokens used by
our Svelte components. Global CSS variables (colours, typography, shadows) are defined in
`src/app.css` via `@layer base`. Components should prefer Tailwind utility classes (including
arbitrary values such as `bg-[var(--color-surface-1)]`) instead of bespoke CSS whenever
possible.

To run the Tailwind-powered build locally:

```bash
pnpm install
pnpm run dev
```

## UI component library

Reusable UI elements live under `apps/web/src/lib/ui`. The SvelteKit project in this module
accesses them through the `$ui` alias (configured in `vite.config.ts` and `tsconfig.json`). Import
components directly from the index module:

```svelte
<script lang="ts">
  import { Card, HeroHeader, KpiCard } from '$ui';
</script>
```

### `Card`
Container primitive that handles surface styling, elevation, and spacing with Tailwind classes.
Props:

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `element` | `keyof HTMLElementTagNameMap` | `'div'` | Underlying HTML element. |
| `padding` | `'sm' \| 'md' \| 'lg' \| 'xl'` | `'lg'` | Adjusts internal Tailwind padding. |
| `variant` | `'surface' \| 'translucent'` | `'translucent'` | Chooses between overlay or frosted backgrounds. |
| `interactive` | `boolean` | `false` | Enables hover and focus affordances. |
| `className` | `string` | `''` | Appends additional Tailwind utilities. |

Example:

```svelte
<Card element="section" padding="md" className="flex flex-col gap-4">
  <h2>Top artists</h2>
  <slot />
</Card>
```

### `KpiCard`
Specialised metric card built on top of `Card`. Provide a `label`, a formatted `value`, and
optionally a short `helper` string shown under the value:

```svelte
<KpiCard label="Total listens" value={total.toLocaleString()} helper="All time" />
```

### `HeroHeader`
Hero-style page header with gradient backdrop. Pass the `title`, `description`, and an
optional alignment (`'center'` or `'start'`). You can also provide an eyebrow slot for a
supporting label and default slot content for actions.

```svelte
<HeroHeader title="Analyzer" description="Library insights at a glance" align="start">
  <span slot="eyebrow">Insights</span>
  <Button slot="default">Open reports</Button>
</HeroHeader>
```

Keep component-specific docs short and colocated when adding new UI primitives so the design
language remains easy to reference.
