# Publishing LMS Docker Alpha

This document describes the steps to build and publish the LMS Docker image with the `alpha` tag.

## Prerequisites
- Docker installed and running.
- Access to the `muma/lms` repository on Docker Hub.
- A Docker Hub Personal Access Token (PAT).

## Publication Steps

1. **Login to Docker Hub**
   Use the following command to log in using the provided PAT:
   ```bash
   echo "<DOCKER_HUB_PAT>" | docker login -u muma --password-stdin
   ```
   *(Note: Replace `<DOCKER_HUB_PAT>` with your actual token)*

2. **Build the Docker Image**
   The `Dockerfile-release` is used for the alpha builds. It includes the multi-stage build for the MuMaFi interface.
   ```bash
   docker build -t muma/lms:alpha -f Dockerfile-release .
   ```

3. **Push the Image**
   Push the built image to Docker Hub:
   ```bash
   docker push muma/lms:alpha
   ```

## Summary Command
To perform build, publish, and automatic deployment to the production server:
```bash
./build_and_publish.sh
```

Alternatively, to perform the steps manually:
1. **Login to Docker Hub**
   ```bash
   echo "<DOCKER_HUB_PAT>" | docker login -u muma --password-stdin
   ```

2. **Build and Push**
   ```bash
   docker build -t muma/lms:alpha -f Dockerfile-release . && \
   docker push muma/lms:alpha
   ```

## Production Update
The `build_and_publish.sh` script automatically handles the update on the production server (`192.0.2.27`).

If you need to perform the update manually on the server:
```bash
docker pull muma/lms:alpha
docker stop lms-alpha || true
docker rm lms-alpha || true
docker run -d --name lms-alpha --restart unless-stopped -p 5082:5082 -v /var/lms:/var/lms -v /music:/music muma/lms:alpha
```
