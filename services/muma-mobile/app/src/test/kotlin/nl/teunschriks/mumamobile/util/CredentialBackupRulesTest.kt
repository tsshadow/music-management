/*
 * CredentialBackupRulesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.w3c.dom.Element

/**
 * The encrypted credential store stays out of Android auto-backup and device transfer (issue #115):
 * its Keystore key never leaves the device, so a copy is useless at best, and the rule makes the
 * restored app signed out on purpose rather than by accident. Reads the resource files themselves;
 * Gradle runs unit tests from the module directory.
 */
class CredentialBackupRulesTest {

    private val credentialFiles = listOf(
        "${SecureSettings.PREFS_FILE}.xml",
        "${SecureSettings.LEGACY_PREFS_FILE}.xml"
    )

    private fun excludedSharedPrefs(file: String, section: String): Set<String> {
        val document = DocumentBuilderFactory.newInstance().newDocumentBuilder()
            .parse(File("src/main/res/xml/$file"))
        val sectionElement = document.getElementsByTagName(section).item(0) as Element
        val excludes = sectionElement.getElementsByTagName("exclude")
        return (0 until excludes.length)
            .map { excludes.item(it) as Element }
            .filter { it.getAttribute("domain") == "sharedpref" }
            .map { it.getAttribute("path") }
            .toSet()
    }

    @Test
    fun `cloud backup excludes the credential store`() {
        excludedSharedPrefs("backup_rules.xml", "cloud-backup")
            .containsAll(credentialFiles) shouldBeEqualTo true
    }

    @Test
    fun `device transfer excludes the credential store`() {
        excludedSharedPrefs("backup_rules.xml", "device-transfer")
            .containsAll(credentialFiles) shouldBeEqualTo true
    }

    @Test
    fun `the pre-Android-12 backup descriptor excludes the credential store`() {
        excludedSharedPrefs("backup_descriptor.xml", "full-backup-content")
            .containsAll(credentialFiles) shouldBeEqualTo true
    }
}
