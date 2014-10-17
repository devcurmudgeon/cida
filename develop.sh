#!/bin/sh

# Set up a development environment in a container.

echo docker run -i -t --rm \
    --volume=`pwd`:/src/test-baserock-infrastructure \
    baserock/openid-provider

