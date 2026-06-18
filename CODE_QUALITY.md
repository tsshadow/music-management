# Code Kwaliteit & Richtlijnen

Dit document beschrijft het pad naar een hogere codekwaliteit, minder bugs en minder regressies binnen het LMS project. We richten ons op automatisering, statische analyse en een robuuste teststrategie.

## 1. Statische Analyse & Linting
Het doel is om fouten te vinden voordat de code wordt uitgevoerd.

### C++ (Backend)
*   **Clang-Tidy**: Reeds geconfigureerd in `.clang-tidy`. Dit moet onderdeel worden van de CI-pijplijn. Het vindt programmeerfouten, stijlproblemen en potentieel onveilige constructies.
*   **Cppcheck**: Een aanvullende tool die zich richt op unieke bugs die compilers vaak missen.
*   **Clang-Format**: Gebruik `.clang-format` om een consistente programmeerstijl af te dwingen. Dit voorkomt onnodige discussies tijdens code reviews.

### TypeScript/Svelte (Frontend)
*   **Oxlint**: Een extreem snelle linter die de meeste ESLint-regels vervangt met veel betere performance. Ideaal voor directe feedback tijdens het typen.
*   **ESLint**: Blijf ESLint gebruiken voor Svelte-specifieke regels die Oxlint (nog) niet ondersteunt.
*   **Oxfmt**: Gebruik dit voor razendsnelle formatting van de frontend code, consistent met de ingestelde regels.

## 2. Teststrategie
We hanteren de testpiramide: veel unit tests, minder integratietests, en een select aantal E2E tests.

### Unit Testing
*   **C++ (GTest)**: Gebruik Google Test voor alle logica in `src/libs`. Elke library moet een bijbehorende `test/` directory hebben met een hoge dekkingsgraad.
*   **Frontend (Vitest)**: Voor de Svelte-componenten en TypeScript-logica. Vitest is zeer snel en integreert perfect met Vite.

### Behavior Driven Development (BDD)
*   **Gherkin / Cucumber**: Gebruik Gherkin-syntax (`Feature`, `Scenario`, `Given`, `When`, `Then`) om functionele eisen vast te leggen. Dit dient als documentatie én als test.
    *   Focus op kernprocessen: "Muziek scannen", "Afspeellijst aanmaken", "Subsonic API authenticatie".

### End-to-End (E2E) Testing
*   **Cypress / Playwright**: Automatiseer de belangrijkste gebruikerspaden in de UI.
    *   *Scenario*: Inloggen -> Zoeken naar artiest -> Nummer afspelen.
    *   Dit garandeert dat de integratie tussen frontend en backend werkt.

## 3. Automatisering (De "Golden Path")

Om de kwaliteit te waarborgen zonder de ontwikkelaar te vertragen:

1.  **Pre-commit Hooks**: We gebruiken de `pre-commit` framework. 
    *   **Installatie**: `pip install pre-commit && pre-commit install`
    *   **Inhoud**: Controleert automatisch `clang-format`, `clang-tidy`, `oxlint` en `oxfmt` bij elke commit.
    *   **Handmatig draaien**: `pre-commit run --all-files`
2.  **Continuous Integration (CI)**:
    *   Elke Pull Request wordt automatisch gecontroleerd via `.github/workflows/lint.yml`.
    *   Alle frontend linting (`oxlint`) en formatting (`oxfmt`) moet slagen.
    *   Backend code moet voldoen aan `clang-format`.
3.  **Code Reviews**: Gebruik de tools om de "saaie" zaken (stijl, kleine bugs) af te vangen, zodat de review kan focussen op architectuur en logica.

## 4. Implementatiepad (Volgende Stappen)

1.  [x] **Stap 1: Statische Analyse & CI**: `oxlint`, `oxfmt` en `clang-format` geïntegreerd in CI en pre-commit hooks.
2.  [ ] **BDD Pilot**: Schrijf één kernfunctionaliteit uit in Gherkin (bijv. de `scanner` library).
3.  [ ] **E2E Setup**: Initialiseer Cypress of Playwright in `src/lms/ui/spotify-ui`.
4.  [ ] **Test Dekking**: GTest integratie in CI voor de backend libraries.
