#!/bin/sh

# Set up a development environment in a container.

exec docker run -i -t --rm \
    --publish=127.0.0.1:80:80 \
    --volume=`pwd`:/src/test-baserock-infrastructure \
    baserock/storyboard

