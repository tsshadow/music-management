/*
 * BondedDevice.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.car

/** One paired Bluetooth device, reduced to what the choice actually depends on. */
data class BondedDevice(val address: String, val name: String?, val isCarClass: Boolean)

/**
 * Which paired devices to tick when the user opens the list for the first time.
 *
 * The device class is a suggestion and the stored set is the answer. Plenty of car kits report
 * neither AUDIO_VIDEO_CAR_AUDIO nor AUDIO_VIDEO_HANDSFREE, and some headsets report the second, so
 * a class check alone is how earbuds end up starting car mode. Once anything is stored, that is
 * returned untouched -- including a deliberate empty set, which is why [stored] is nullable rather
 * than an empty check at the call site.
 */
fun preTickedCarDevices(bonded: List<BondedDevice>, stored: Set<String>?): Set<String> {
    if (stored != null) return stored
    return bonded.filter { it.isCarClass }.map { it.address }.toSet()
}
