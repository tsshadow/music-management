include(GoogleTest)

add_executable(test-muma
	Authentication.cpp
	PathEncoding.cpp
	Routing.cpp
	)

target_link_libraries(test-muma PRIVATE
	lmsmuma
	GTest::GTest
	)

if (NOT CMAKE_CROSSCOMPILING)
	gtest_discover_tests(test-muma)
endif()
