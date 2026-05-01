add_library(lmsjukebox STATIC
	impl/JukeboxService.cpp
	)

target_include_directories(lmsjukebox INTERFACE
	include
	)

target_include_directories(lmsjukebox PRIVATE
	include
	impl
	)

target_link_libraries(lmsjukebox PRIVATE
	lmsaudio	
	lmscore
	lmsdatabase
	)

target_link_libraries(lmsjukebox PUBLIC
	lmscore
	)
