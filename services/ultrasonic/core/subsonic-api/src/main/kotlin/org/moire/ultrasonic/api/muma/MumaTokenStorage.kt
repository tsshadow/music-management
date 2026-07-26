package org.moire.ultrasonic.api.muma

interface MumaTokenStorage {
    var mumaAccessToken: String?
    var mumaRefreshToken: String?
}
