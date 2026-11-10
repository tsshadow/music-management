
add_library(lmsmumaoutbox STATIC
	impl/MumaOutboxRelay.cpp
	)

target_include_directories(lmsmumaoutbox INTERFACE
	include
	)

target_include_directories(lmsmumaoutbox PRIVATE
	include
	impl
	)

# Public: the interface takes a core::http::IClient and a database::mumaRatingOutbox::Key.
target_link_libraries(lmsmumaoutbox PUBLIC
	lmscore
	lmsdatabase
	)

if(BUILD_TESTING)
	add_subdirectory(test)
endif()
