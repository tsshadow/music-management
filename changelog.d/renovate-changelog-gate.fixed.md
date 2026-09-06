- **Elke merge request van Renovate bleef rood op `muma:changelog`.** Het script eist een
  changelog-fragment van iedere merge request, en Renovate schrijft die niet — er is aan die kant
  niemand om aan iets te herinneren. Het gevolg was niet alleen een rood vinkje: de meeste van die
  merge requests horen zichzelf te mergen, en een gate die nooit groen wordt zet die automerge
  gewoon stil, zodat de bumps blijven liggen tot iemand ze met de hand `no-changelog` geeft.
  `renovate/*` is nu een vrijstelling zoals `release/*` en de back-merge dat al waren. Een
  dependency-bump die wél een regel verdient, is er een die iemand gelezen heeft, en die kan het
  fragment toevoegen zoals op elke andere branch.
