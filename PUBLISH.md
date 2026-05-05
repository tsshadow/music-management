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
   The `Dockerfile-release` is used for the alpha builds. It includes the multi-stage build for the Spotify UI.
   ```bash
   docker build -t muma/lms:alpha -f Dockerfile-release .
   ```

3. **Push the Image**
   Push the built image to Docker Hub:
   ```bash
   docker push muma/lms:alpha
   ```

## Summary Command
To perform all steps at once:
```bash
echo "<DOCKER_HUB_PAT>" | docker login -u muma --password-stdin && \
docker build -t muma/lms:alpha -f Dockerfile-release . && \
docker push muma/lms:alpha
```

## Production Update
After pushing, the production server (e.g., `192.0.2.27`) needs to pull the new image and recreate the container:
```bash
docker pull muma/lms:alpha
docker stop lms_alpha
docker rm lms_alpha
docker run -d --name lms_alpha --restart unless-stopped -p 5082:5082 -v /var/lms:/var/lms -v /music:/music muma/lms:alpha
```
