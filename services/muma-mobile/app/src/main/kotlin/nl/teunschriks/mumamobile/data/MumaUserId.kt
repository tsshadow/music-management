/*
 * MumaUserId.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

/**
 * Whether an account id from the MuMa backend is one that could name an actual row.
 *
 * `users.id` is `AUTO_INCREMENT`, so a real id starts at 1. Anything below that is either the -1
 * "not known yet" sentinel or Gson's default for a field the response never carried. The guards
 * used to test for -1 alone, so a 0 -- which is what a login response read with the wrong model
 * produced -- passed all of them, and every per-user request addressed `/api/users/0/...`.
 *
 * It lives outside [ActiveServerProvider] on purpose: loading that class runs an initializer that
 * needs Android, and this is a rule about a number.
 */
fun isUsableMumaUserId(userId: Int?): Boolean = userId != null && userId > 0
