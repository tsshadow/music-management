- **The app's account-settings writes no longer overwrite the web player's** (issue #39, bug report
  116). Favourite genres and the one-off bookmark migration into set resume used to read the whole
  account settings blob and post it back, dropping anything another device saved in between. They
  now send only their own key with the server's new per-key `PATCH`, and fall back to the old
  whole-blob write against a server that answers it with 405. The web UI inside the app gets the
  same change through the web player's own settings sync.
<!-- release notes -->
- Settings changed in the app and in the web player at the same time no longer overwrite each
  other.
