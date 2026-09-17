- **De web-UI wordt nu per merge request op desktop én telefoon gerenderd en vergeleken.**
  `frontend:e2e` draait de browsersuite voortaan in twee Playwright-projecten (`desktop`
  1280×800, `phone` 412×915) en maakt van negentien routes een screenshot die tegen de referenties
  in `services/frontend/tests/browser/__screenshots__/` wordt gelegd. Een afwijking kleurt de job
  oranje (exit 42, `allow_failure`) en laat het verschil als artifact achter; een functionele
  fout blijft rood. De referenties zijn tegelijk de schermafbeeldingen van de app —
  zie `docs/frontend-screenshots.md` voor verversen na een bedoelde wijziging
  (`MUMA_UPDATE_SNAPSHOTS=1` en `scripts/test/frontend-screenshots-pull.sh`).
<!-- release notes -->
- De web-UI wordt bij elke wijziging op desktop en telefoon gerenderd en vergeleken met een vaste
  set schermafbeeldingen, zodat een kapotte layout opvalt voordat hij live staat.
