
add_library(lmsmuma STATIC
    MumaResource.cpp
    PathEncoding.cpp
)

target_include_directories(lmsmuma INTERFACE
    include
)

target_include_directories(lmsmuma PRIVATE
    include
)

target_link_libraries(lmsmuma PRIVATE
    lmscore
    lmsdatabase
    lmsauth
    lmsscanner
    Wt::Wt
)

if(BUILD_TESTING)
    add_subdirectory(test)
endif()
