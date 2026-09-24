
add_library(lmsmuma STATIC
    Authentication.cpp
    MumaResource.cpp
    PathEncoding.cpp
)

target_include_directories(lmsmuma INTERFACE
    include
)

target_include_directories(lmsmuma PRIVATE
    include
    # Header-only endpoints/UserSettingsValidation.hpp: the Subsonic token length floor, shared
    # with /updateUser so both ways of issuing a token enforce the same rule.
    ../subsonic/impl
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
