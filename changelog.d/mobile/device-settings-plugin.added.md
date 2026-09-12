- **`MumaSystem` beantwoordt de nieuwe instellingen-tab van de webspeler.** `getSettings()` geeft
  een momentopname van de instellingen die de tab toont; `setSetting({key, value})` schrijft er één
  terug, tegen een vaste whitelist met een typecontrole — een onbekende sleutel of een verkeerd
  type wordt geweigerd in plaats van een instelling stilzwijgend niets te laten doen. `MumaStorage`
  kreeg er `clearCache()` bij: annuleert wachtende en actieve downloads en verwijdert daarna elk
  gecachet bestand dat niet is vastgezet.
