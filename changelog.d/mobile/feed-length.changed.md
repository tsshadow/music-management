- **Android Auto's feed folders list 100 tracks instead of 30**, following the server's new default
  feed length. A feed longer than 100 (the server allows up to 200) is resolved in chunks of 100,
  the most the streaming server accepts per `getSongsByPath` call; before, such a feed would have
  come back empty.
<!-- release notes -->
- Release Radar and the daily mixes in the car now hold 100 tracks instead of 30.
