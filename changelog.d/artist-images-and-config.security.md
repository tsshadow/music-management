- **`POST /api/config` echoed secrets in the clear.** The response carried the real value of every
  posted key; it now carries the masked value the GET shows. API consumers that read the response
  body receive the sentinel for secrets (the web config page reloads the fields and is unaffected).
