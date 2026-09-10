- **`canonicalOnly` is een filter in de query geworden, geen lus die pagina's bij elkaar scant.** De
  webspeler klapt rijen samen door in batches door te scannen tot een pagina vol is — dat moest, want
  de oude heuristiek was niet in SQL uit te drukken. `is_canonical` wel: één predicate in de gedeelde
  queryopbouw van `find_advanced` en `countAdvanced`, waardoor paginering, sorteren én tellen het
  onderling eens blijven.
- Het predicate laat een track zonder groepering expliciet staan
  (`is_canonical <> 0 OR work_id IS NULL`). Alleen op `is_canonical` filteren zou de helft van de
  bibliotheek laten verdwijnen zolang de worker zijn achterstand wegwerkt.
- Een `workId` schakelt het filter uit: alle versies van één nummer opvragen en samenklappen tot één
  ervan zijn tegengestelden, en dat mag niet van de volgorde van parameters afhangen.
