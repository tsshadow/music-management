#!/bin/bash
# scripts/ci/cpp-tidy-image.sh
# Shared helper: makes sure the clang-tidy toolchain image exists, and exports
# CPP_TIDY_IMAGE with its tag. Source it, do not execute it.
#
#   source "$ROOT_DIR/scripts/ci/cpp-tidy-image.sh"
#   docker run --rm -u "$(id -u):$(id -g)" ... "$CPP_TIDY_IMAGE" ...
#
# Same shape as scripts/ci/android-image.sh, for the same reasons: the image
# carries a pile of -dev packages that take minutes to install, so installing
# them per run would dominate the job, and it runs as the caller's uid so the
# build directory it writes is not root-owned.
#
# The tag carries a hash of the Dockerfile, so editing that file produces a new
# tag and therefore a rebuild -- a fixed tag would silently keep serving the
# stale image forever.

_cpp_tidy_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_cpp_tidy_dockerfile="$_cpp_tidy_root/docker/Dockerfile-cpp-tidy"
_cpp_tidy_tag="19-$(sha256sum "$_cpp_tidy_dockerfile" | cut -c1-12)"

CPP_TIDY_IMAGE="music-management/cpp-tidy:${_cpp_tidy_tag}"
export CPP_TIDY_IMAGE

if ! docker image inspect "$CPP_TIDY_IMAGE" >/dev/null 2>&1; then
    echo "--- Building $CPP_TIDY_IMAGE (one-off; the toolchain is baked in) ---"
    docker build -f "$_cpp_tidy_dockerfile" \
        --build-arg RUNNER_UID="$(id -u)" \
        --build-arg RUNNER_GID="$(id -g)" \
        -t "$CPP_TIDY_IMAGE" \
        "$_cpp_tidy_root/docker/"
fi

unset _cpp_tidy_root _cpp_tidy_dockerfile _cpp_tidy_tag
