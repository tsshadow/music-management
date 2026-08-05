package nl.teunschriks.mumamobile.api.muma

interface MumaTokenStorage {
    var mumaAccessToken: String?
    var mumaRefreshToken: String?
}
