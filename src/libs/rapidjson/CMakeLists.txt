set(HEADER_FILES *.h)

add_library(rapidjson ${HEADER_FILES})


target_include_directories(rapidjson INTERFACE
        include
)

target_include_directories(rapidjson PRIVATE
        include
)