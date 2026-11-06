# Local Android test run breaks the Android jobs on the runner host

# status: fixed

# reported problem

`mobile:format` and `mobile:lint` failed on the runner host `minipc-debian13` with
`Failed to apply plugin 'com.android.internal.application'` and the single line `/home/ci/.android`.
The log also has `Unable to initialize metrics, ensure /home/ci/.android is writable`. A retry
failed in the same way. The same jobs passed earlier on the same day.

# Possible reason

The runner host is also the machine where sessions run the local test scripts, with one Docker
daemon. `scripts/ci/android-image.sh` builds the image when the tag is missing, and sets the owner of
`/home/ci` to the uid that runs the script. The tag had only the hash of the Dockerfile. The janitor
removed the image, a local test as uid 1000 built it again, and the runner as uid 997 got an image
where it cannot write to `/home/ci`. Measured: `stat /home/ci` in the image gave `1000:1000 755`.

# solution

The tag now includes the uid (`37-<hash>-uid<uid>`), so each user gets an image of their own. To
recover the host at the time, the image with the wrong owner was removed, and the next job built it
again as the runner. `tests/ci/test_android_image_per_uid.py` holds the tag format.
