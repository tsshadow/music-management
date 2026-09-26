- **An artist image URL could still reach the internal network through DNS rebinding.** "Set
  image from URL" checked the host's addresses and then let `requests` resolve the name again, so
  a DNS server answering public for the check and `192.0.2.27` or `169.254.169.254` for the
  fetch got the download past it. The host is now resolved once, every address is checked
  (including CGNAT, Docker/LAN ranges and IPv6 forms that embed a private IPv4 address), and the
  connection goes to that checked address with the original name as `Host`, TLS server name and
  certificate name. Every redirect hop is checked the same way, at most three. The bulk portrait
  fetcher downloads provider image URLs through the same path, where it had no address check or
  size cap before. Bug report 114.
<!-- release notes -->
- Artist image downloads can no longer be steered to an internal address by a DNS server that
  changes its answer between the check and the download.
