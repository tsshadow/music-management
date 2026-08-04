package nl.teunschriks.mumamobile

import com.tngtech.archunit.core.importer.ImportOption
import com.tngtech.archunit.junit.AnalyzeClasses
import com.tngtech.archunit.junit.ArchTest
import com.tngtech.archunit.lang.ArchRule
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses

@AnalyzeClasses(packages = ["nl.teunschriks.mumamobile"], importOptions = [ImportOption.DoNotIncludeTests::class])
class ArchitectureTest {

    @ArchTest
    val domainShouldNotDependOnAndroid: ArchRule = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat().resideInAPackage("android..")
        .because("Domain layer should be platform-independent")

    @ArchTest
    val apiShouldNotDependOnAndroid: ArchRule = noClasses()
        .that().resideInAPackage("..api..")
        .should().dependOnClassesThat().resideInAPackage("android..")
        .because("API layer should be platform-independent")
}
