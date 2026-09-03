<script>
  import MumaMark from './MumaMark.svelte';

  // The player/management toggle used to live here. Management is now an entry in
  // the profile menu, so switching to it is a normal navigation with its own URL
  // and the browser's back button is the way out -- which is what a toggle that
  // sat in three different sidebars could never be.
</script>

<div class="px-4 pt-5 pb-2 flex flex-col gap-5">
  <div class="flex items-center gap-2 text-xl font-bold text-white px-2">
    <div class="w-8 h-8 bg-brand rounded-full flex items-center justify-center text-black">
      <MumaMark size={18} />
    </div>
    <span>MuMa</span>
  </div>
</div>
