
add_library(lmsmuma STATIC
    MumaResource.cpp
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
