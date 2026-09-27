<script>
  /**
   * The inline throbber: a small spinning ring in the current text colour. It marks an action
   * that is waiting (play pressed before the tracks arrived) or a background refresh next to a
   * heading -- never a whole page or section, which get skeletons (styleguide, Loading States).
   */
  import { t } from '../i18n/index.js';

  const { size = 16, label = '' } = $props();
</script>

<span
  class="inline-block shrink-0 rounded-full border-2 border-current border-t-transparent animate-spin align-middle"
  style="width: {size}px; height: {size}px"
  role="status"
  aria-label={label || $t('common.loading')}
  data-testid="throbber"
></span>
