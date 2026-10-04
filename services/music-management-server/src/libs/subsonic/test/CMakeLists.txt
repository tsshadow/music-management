include(GoogleTest)

add_executable(test-subsonic
	AuthCache.cpp
	ClientInfo.cpp
	FestivalLineup.cpp
	Memories.cpp
	ParameterRedaction.cpp
	ScanScope.cpp
	SongsByPath.cpp
	SpotifyPaging.cpp
	Subsonic.cpp
	SubsonicResponse.cpp
	TrackForm.cpp
	TranscodeDecision.cpp
	UserSettingsValidation.cpp
	)

target_include_directories(test-subsonic PRIVATE
	../impl
	)

target_link_libraries(test-subsonic PRIVATE
	lmscore
	lmsaudio
	# The memories endpoint's header names db::TrackId, and lmssubsonic links lmsdatabase
	# privately, so the test target needs the database headers in its own right.
	lmsdatabase
	lmssubsonic
	GTest::GTest
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-subsonic)
endif()

