include(GoogleTest)

add_executable(test-feedback
	FeedbackService.cpp
	# The service reads and writes ratings in a real database. Reuses the fixture the database
	# tests already build against, as test-auth does.
	../../../database/test/Common.cpp
	)

target_link_libraries(test-feedback PRIVATE
	lmscore
	lmsfeedback
	lmsdatabase
	GTest::GTest
	)

target_include_directories(test-feedback PRIVATE
	../impl
	../../../database/test
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-feedback)
endif()
