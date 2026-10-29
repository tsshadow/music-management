- **Guava goes from 33.3.1 to 33.7.2.** media3 pulls in Guava 33.3.1, which has CVE-2026-102554, a
  denial of service rated high. A constraint in `app/build.gradle` raises it to 33.7.2-android;
  `dependencyInsight` shows every request in the release classpath (31.1, 32.0.0-jre, 33.3.1)
  resolving to that version. Drop the constraint once media3 asks for 33.7.2 or later.
<!-- release notes -->
- Security update for a library the player uses.
