
add_executable(lms
	main.cpp
	LmsInitApplication.cpp
	)

target_include_directories(lms PRIVATE
	.
	)

target_link_libraries(lms PRIVATE
	Boost::iostreams
	Wt::Wt
	Wt::HTTP
	lmsartwork
	lmsaudio
	lmsauth
	lmscore
	lmsdatabase
	lmsfeedback
	lmsjukebox
	lmsmuma
	lmspodcast
	lmsrecommendation
	lmsscanner
	lmsscrobbling
	lmssubsonic
	lmstranscoding
	)

install(TARGETS lms DESTINATION bin)
