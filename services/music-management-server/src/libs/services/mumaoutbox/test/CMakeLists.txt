include(GoogleTest)

add_executable(test-mumaoutbox
	Main.cpp
	MumaOutboxRelay.cpp
	# The relay reads and writes both outboxes in a real database. Reuses the fixture the database
	# tests already build against, as test-scrobbling does.
	../../../database/test/Common.cpp
	)

target_link_libraries(test-mumaoutbox PRIVATE
	lmscore
	lmsmumaoutbox
	lmsdatabase
	GTest::GTest
	)

target_include_directories(test-mumaoutbox PRIVATE
	../impl
	../../../database/test
	# FakeHttpClient.hpp: the relay's requests are recorded, never sent.
	../../../core/test
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-mumaoutbox)
endif()
