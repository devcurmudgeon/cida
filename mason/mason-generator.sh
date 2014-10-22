#!/bin/sh

set -e

if [ "$#" -lt 5 -o "$#" -gt 6 -o "$1" == "-h" -o "$1" == "--help" ]; then
  cat <<EOF
Usage:
    `basename $0` HOST_PREFIX UPSTREAM_TROVE_HOSTNAME VM_USER VM_HOST VM_PATH [HOST_POSTFIX]

Where:
  HOST_PREFIX              -- Name of your Mason instance
                              e.g. "my-mason" to produce hostnames:
                              my-mason-trove and my-mason-controller
  UPSTREAM_TROVE_HOSTNAME  -- Upstream trove's hostname
  VM_USER                  -- User on VM host for VM deployment
  VM_HOST                  -- VM host for VM deployment
  VM_PATH                  -- Path to store VM images in on VM host
  HOST_POSTFIX             -- e.g. ".example.com" to get
                              my-mason-trove.example.com

This script makes deploying a Mason system simpler by automating
the generation of keys for the systems to use, building of the
systems, filling out the mason deployment cluster morphology
template with useful values, and finally deploying the systems.

To ensure that the deployed system can deploy test systems, you
must supply an ssh key to the VM host.  Do so with the following
command:
  ssh-copy-id -i ssh_keys-HOST_PREFIX/worker.key.pub VM_USER@VM_HOST

To ensure that the mason can upload artifacts to the upstream trove,
you must supply an ssh key to the upstream trove.  Do so with the
following command:
  ssh-copy-id -i ssh_keys-HOST_PREFIX/id_rsa.key.pub root@UPSTREAM_TROVE_HOSTNAME

EOF
  exit 0
fi


HOST_PREFIX="$1"
UPSTREAM_TROVE="$2"
VM_USER="$3"
VM_HOST="$4"
VM_PATH="$5"
HOST_POSTFIX="$6"

sedescape() {
    # Escape all non-alphanumeric characters
    printf "%s\n" "$1" | sed -e 's/\W/\\&/g'
}


##############################################################################
# Key generation
##############################################################################

mkdir -p "ssh_keys-${HOST_PREFIX}"
cd "ssh_keys-${HOST_PREFIX}"
test -e mason.key || ssh-keygen -t rsa -b 2048 -f mason.key -C mason@TROVE_HOST -N ''
test -e lorry.key || ssh-keygen -t rsa -b 2048 -f lorry.key -C lorry@TROVE_HOST -N ''
test -e worker.key || ssh-keygen -t rsa -b 2048 -f worker.key -C worker@TROVE_HOST -N ''
test -e id_rsa || ssh-keygen -t rsa -b 2048 -f id_rsa -C trove-admin@TROVE_HOST -N ''
cd ../


##############################################################################
# Mason setup
##############################################################################

cp clusters/mason.morph mason-${HOST_PREFIX}.morph

sed -i "s/red-box-v1/$(sedescape "$HOST_PREFIX")/g" "mason-$HOST_PREFIX.morph"
sed -i "s/ssh_keys/ssh_keys-$(sedescape "$HOST_PREFIX")/g" "mason-$HOST_PREFIX.morph"
sed -i "s/upstream-trove/$(sedescape "$UPSTREAM_TROVE")/" "mason-$HOST_PREFIX.morph"
sed -i "s/vm-user/$(sedescape "$VM_USER")/g" "mason-$HOST_PREFIX.morph"
sed -i "s/vm-host/$(sedescape "$VM_HOST")/g" "mason-$HOST_PREFIX.morph"
sed -i "s/vm-path/$(sedescape "$VM_PATH")/g" "mason-$HOST_PREFIX.morph"
sed -i "s/\.example\.com/$(sedescape "$HOST_POSTFIX")/g" "mason-$HOST_PREFIX.morph"


##############################################################################
# System building
##############################################################################

morph build systems/trove-system-x86_64.morph
morph build systems/build-system-x86_64.morph


##############################################################################
# System deployment
##############################################################################

morph deploy mason-${HOST_PREFIX}.morph


##############################################################################
# Cleanup
##############################################################################

rm mason-${HOST_PREFIX}.morph
