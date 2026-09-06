- **De back-merge naar develop faalde bij elke release op `muma:changelog`.** Dat script eist een
  fragment van elke merge request, met een uitzondering voor `release/*` en `hotfix/*` — maar niet
  voor de merge request die master terugbrengt naar develop. Die voegt per definitie niets toe: de
  fragmenten die hij zou moeten dragen zijn net door de release opgegeten. Het gevolg is groter dan
  een rood vinkje, want een back-merge die niet kan mergen blijft openstaan, en een openstaande
  back-merge onderdrukt de branch-pipeline van master — waarmee de eerstvolgende release zijn tag
  én zijn eigen back-merge verliest. `master` → `develop` is nu net zo'n uitzondering als een
  release-branch, met tests voor alle vrijstellingen erbij; een branch die alleen "master" in zijn
  naam heeft, valt er niet onder.
