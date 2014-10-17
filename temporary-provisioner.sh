#!/bin/sh

# Temporary provisioner for the Baserock OpenID provider.
# This should be done with Ansible really (or perhaps
# Puppet, since it looks like Puppet will be the quickest
# route to getting Storyboard up ...)

# I'd like to use Python 3 for this, but seems that
# django_openid_provider needs fixing for Python 3.

yum install python-pip --assumeyes
pip install django django_openid_provider python-openid


