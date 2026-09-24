- **LMS could read freed memory when a client hung up on a slow artist picture.** The `getCoverArt`
  proxy to MuMa kept a raw pointer to Wt's response continuation, and Wt frees that continuation
  when the client disconnects. If MuMa's answer or the 504 deadline landed after that, it went
  through the dangling pointer. The proxy now holds the continuation weakly and does nothing once it
  is gone. Normal completion still cancels the deadline. Bug report 066.

<!-- release notes -->

- **Fixed a possible server crash when an artist picture was still loading as you scrolled past it.**
