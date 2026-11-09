- **The Android build-config check passed its refusal cases when Gradle never started.** Any
  non-zero exit counted as the expected refusal, so a docker error or a broken wrapper also looked
  green. Each refusal case now needs the message Gradle prints for it (#196).
