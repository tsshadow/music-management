pkg_check_modules(LIBAV IMPORTED_TARGET libavcodec libavutil libavformat libswresample)
pkg_check_modules(Taglib REQUIRED IMPORTED_TARGET taglib)
pkg_check_modules(PulseAudio REQUIRED IMPORTED_TARGET libpulse)

add_library(lmsaudio STATIC
	impl/ffmpeg/AudioFile.cpp
	impl/ffmpeg/AudioFileInfo.cpp
	impl/ffmpeg/AudioFileInfoParser.cpp
	impl/ffmpeg/FFmpegTypes.cpp
	impl/ffmpeg/ImageReader.cpp
	impl/ffmpeg/PcmDecoder.cpp
	impl/ffmpeg/TagReader.cpp
	impl/ffmpeg/Transcoder.cpp
	impl/ffmpeg/Utils.cpp
	impl/pulseaudio/AudioOutput.cpp
	impl/pulseaudio/AudioOutputStream.cpp
	impl/pulseaudio/Exception.cpp
	impl/pulseaudio/MainLoopScopedLock.cpp
	impl/taglib/AudioFileInfo.cpp
	impl/taglib/AudioFileInfoParser.cpp
	impl/taglib/ImageReader.cpp
	impl/taglib/TagReader.cpp
	impl/taglib/Utils.cpp
	impl/AudioFileInfoParser.cpp
	impl/PcmTypes.cpp
	impl/TagReader.cpp
	)

target_include_directories(lmsaudio INTERFACE
	include
	)

target_include_directories(lmsaudio PRIVATE
	include
	${AVCODEC_INCLUDE_DIR}
	${AVFORMAT_INCLUDE_DIR}
	${AVUTIL_INCLUDE_DIR}
	)

target_link_libraries(lmsaudio PUBLIC
	lmscore
	std::filesystem
	)

target_link_libraries(lmsaudio PRIVATE
	PkgConfig::LIBAV
	PkgConfig::Taglib
	PkgConfig::PulseAudio
	)
