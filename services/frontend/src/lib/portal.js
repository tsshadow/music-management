/**
 * Svelte action that moves an element to the end of `document.body`.
 *
 * A `position: fixed` overlay is only fixed to the viewport while none of its ancestors sets
 * `transform`, `filter` or `backdrop-filter`; any of those makes that ancestor the containing
 * block instead. Both top bars in `TopBar.svelte` are `backdrop-blur-md`, so a `Modal` rendered
 * from inside them -- the logout confirmation in `ProfileButton.svelte` -- would be clipped to the
 * bar. Moving the node out keeps the overlay full-screen without the caller having to live
 * elsewhere in the tree. Svelte still owns the node and removes it when its block ends.
 *
 * @param {HTMLElement} node - The element to move.
 * @returns {{ destroy(): void }}
 */
export function portal(node) {
  document.body.appendChild(node);
  return {
    destroy() {
      node.remove();
    },
  };
}
