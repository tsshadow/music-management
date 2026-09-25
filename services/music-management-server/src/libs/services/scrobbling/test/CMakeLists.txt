
add_executable(test-scrobbling
	Listenbrainz.cpp
	MusicManagementBackend.cpp
	Scrobbling.cpp
	# The MuMa relay reads the user and track it reports from a real database. Reuses the fixture
	# the database tests already build against, as test-auth does.
	../../../database/test/Common.cpp
	)

target_link_libraries(test-scrobbling PRIVATE
	lmscore
	lmsscrobbling
	lmsdatabase
	GTest::GTest
	)

target_include_directories(test-scrobbling PRIVATE
	../impl
	../../../database/test
	# FakeHttpClient.hpp, and http/RetryPolicy.hpp to pin how the send queue treats a relayed listen.
	../../../core/test
	../../../core/impl
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-scrobbling)
endif()
