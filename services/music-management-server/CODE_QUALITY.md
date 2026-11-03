# Code Quality and Guidelines

This document describes the path to higher code quality, fewer bugs and fewer regressions in the LMS project. It focuses on automation, static analysis and a solid test strategy.

## 1. Static Analysis and Linting
The goal is to find errors before the code runs.

### C++ (Backend)
*   **Clang-Tidy**: Already configured in `.clang-tidy`. It must become part of the CI pipeline. It finds programming errors, style problems and potentially unsafe constructs.
*   **Cppcheck**: A second tool that looks for bugs compilers often miss.
*   **Clang-Format**: Use `.clang-format` to enforce one consistent code style. This avoids pointless discussion in code reviews.

### TypeScript/Svelte (Frontend)
*   **Oxlint**: An extremely fast linter that replaces most ESLint rules with much better performance. Good for direct feedback while typing.
*   **ESLint**: Keep using ESLint for Svelte-specific rules that Oxlint does not support (yet).
*   **Oxfmt**: Use it for very fast formatting of the frontend code, following the configured rules.

## 2. Test Strategy
We follow the test pyramid: many unit tests, fewer integration tests and a select number of E2E tests.

### Unit Testing
*   **C++ (GTest)**: Use Google Test for all logic in `src/libs`. Each library needs a matching `test/` directory with high coverage.
*   **Frontend (Vitest)**: For the Svelte components and TypeScript logic. Vitest is very fast and works well with Vite.

### Behavior Driven Development (BDD)
*   **Gherkin / Cucumber**: Use Gherkin syntax (`Feature`, `Scenario`, `Given`, `When`, `Then`) to write down functional requirements. It serves as documentation and as a test.
    *   Focus on core processes: "Scan music", "Create a playlist", "Subsonic API authentication".

### End-to-End (E2E) Testing
*   **Cypress / Playwright**: Automate the most important user paths in the UI.
    *   *Scenario*: Log in, search for an artist, play a track.
    *   This makes sure the frontend and the backend work together.

## 3. Automation (the "Golden Path")

To protect quality without slowing the developer down:

1.  **Pre-commit Hooks**: We use the `pre-commit` framework.
    *   **Install**: `pip install pre-commit && pre-commit install`
    *   **Contents**: Runs `clang-format`, `clang-tidy`, `oxlint` and `oxfmt` on each commit.
    *   **Run by hand**: `pre-commit run --all-files`
2.  **Continuous Integration (CI)**:
    *   Each merge request is checked automatically by the CI pipeline.
    *   All frontend linting (`oxlint`) and formatting (`oxfmt`) must pass.
    *   Backend code must pass `clang-format`.
3.  **Code Reviews**: Use the tools to catch the boring things (style, small bugs), so the review can focus on architecture and logic.

## 4. Next Steps

1.  [x] **Step 1: Static analysis and CI**: `oxlint`, `oxfmt` and `clang-format` are part of CI and the pre-commit hooks.
2.  [ ] **BDD pilot**: Write out one core feature in Gherkin (for example the `scanner` library).
3.  [ ] **E2E setup**: Set up Cypress or Playwright in `src/lms/ui/ui`.
4.  [ ] **Test coverage**: Add GTest to CI for the backend libraries.
