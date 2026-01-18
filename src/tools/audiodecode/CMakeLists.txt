
add_executable(lms-audiodecode
	LmsAudioDecode.cpp
	)

target_link_libraries(lms-audiodecode PRIVATE
	lmsaudio
	lmscore
	Boost::program_options
	)
