include(GoogleTest)

add_executable(test-muma
	PathEncoding.cpp
	)

target_link_libraries(test-muma PRIVATE
	lmsmuma
	GTest::GTest
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-muma)
endif()
