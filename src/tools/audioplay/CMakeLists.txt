
add_executable(lms-audioplay
	LmsAudioPlay.cpp
	)

target_link_libraries(lms-audioplay PRIVATE
	lmsaudio
	lmscore
	Boost::program_options
	)

install(TARGETS lms-audioplay DESTINATION bin)