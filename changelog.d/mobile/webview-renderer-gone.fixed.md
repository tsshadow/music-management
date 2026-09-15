- **Zwart scherm na een tijdje wegblijven.** Android ruimt de renderer van een WebView op de
  achtergrond op; niemand ving `onRenderProcessGone`, dus gold de standaard: het hele proces
  afgebroken zodra de app weer in beeld kwam. `CapacitorActivity` maakt de activity nu opnieuw
  aan; de webkant leest sessie en wachtrij terug uit de service, dus afspelen loopt door.

<!-- release notes -->

- **Geen zwart scherm meer** als je de app na een tijdje weer opent.
