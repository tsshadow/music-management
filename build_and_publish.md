To build and publish the LMS Docker image with the `alpha` tag, run the following command:

```bash
./build_and_publish.sh
```

Alternatively, you can run the commands manually:

```bash
docker build -t muma/lms:alpha -f Dockerfile-release . && docker push muma/lms:alpha
```
