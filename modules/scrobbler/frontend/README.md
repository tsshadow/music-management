# Frontend style guide

This frontend shares design tokens and UI primitives with other web modules so that future
features (for example the rating or rule editor) inherit the same look and feel.

## Theme tokens

The shared theme lives in `apps/web/src/lib/theme.css`. Import it once inside
`src/app.css` (or the entry stylesheet of another module) using the Vite alias:

```css
@import '$design/theme.css';
```

The file exposes CSS custom properties for colours, typography, spacing, radii, and shadows.
Dark mode is the default. Switching to the light theme only requires setting a `data-theme`
attribute on the `<body>` (or any parent element):

```html
<body data-theme="light">
  <!-- content -->
</body>
```

The theme also exposes legacy aliases (`--text-color`, `--accent-color`) to remain compatible
with older components while we gradually migrate them to the new naming scheme.

## UI component library

Reusable UI elements now live under `apps/web/src/lib/ui`. The SvelteKit project in this
module accesses them through the `$ui` alias (configured in `vite.config.ts` and
`tsconfig.json`). Import components directly from the index module:

```svelte
<script lang="ts">
  import { Card, HeroHeader, KpiCard } from '$ui';
</script>
```

### `Card`
Container primitive that handles surface styling, elevation, and spacing. It accepts the
props below:

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `element` | `keyof HTMLElementTagNameMap` | `'div'` | Underlying HTML element. |
| `padding` | `'sm' \| 'md' \| 'lg' \| 'xl'` | `'lg'` | Applies theme spacing tokens. |
| `variant` | `'surface' \| 'translucent'` | `'translucent'` | Chooses the background style. |
| `interactive` | `boolean` | `false` | Enables hover and focus affordances. |
| `className` | `string` | `''` | Appends custom classes. |

Example:

```svelte
<Card element="section" padding="md" className="panel">
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
