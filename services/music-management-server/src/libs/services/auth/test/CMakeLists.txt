add_executable(test-auth
	AuthTokenReadPath.cpp
	CaseInsensitiveLogin.cpp
	MusicManagementPasswordOutcome.cpp
	DisabledUser.cpp
	MumaUserSync.cpp
	# AuthTokenReadPath needs a real database behind the service. Reuses the fixture the database
	# tests already build against rather than standing up a second one.
	../../../database/test/Common.cpp
	)

target_link_libraries(test-auth PRIVATE
	lmscore
	lmsauth
	lmsdatabase
	GTest::GTest
	)

target_include_directories(test-auth PRIVATE
	../impl
	../../../database/test
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-auth)
endif()
