add_executable(test-auth
	MusicManagementPasswordOutcome.cpp
	)

target_link_libraries(test-auth PRIVATE
	lmscore
	lmsauth
	GTest::GTest
	)

target_include_directories(test-auth PRIVATE
	../impl
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-auth)
endif()
