- **Elke afgeronde map werd een eigen scanverzoek aan LMS.** Zodra de melding in 0.49.0
  daadwerkelijk aankwam, logde LMS er vijf per seconde, urenlang — één per map die de tagger
  afrondde. Hij overleeft dat, want zijn eigen verzamelaar voegt de paden toch samen, maar elk
  verzoek bezet een Wt-thread en een uitgeputte Wt-threadpool is precies hoe deze server eerder
  de hele site 504's heeft laten geven. De wachtrij vertrekt nu als één verzoek met alle paden
  die er al in stonden, dubbele eruit. Er wordt nergens op gewacht: het punt van die wachtrij is
  dat een verplaatsing nooit blijft hangen op een muziekserver.
