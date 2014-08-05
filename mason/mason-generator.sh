#!/bin/sh

set -e

if [ "$1" == "-h" -o "$1" == "--help" ]; then
  echo "Usage:"
  echo "  `basename $0` HOST_PREFIX UPSTREAM_TROVE_HOSTNAME VM_USER VM_HOST VM_PATH [HOST_POSTFIX]"
  echo ""
  echo "Where:"
  echo "  HOST_PREFIX              -- Name of your Mason instance"
  echo "                              e.g. \"my-mason\" to produce hostnames:"
  echo "                              my-mason-trove and my-mason-controller"
  echo "  UPSTREAM_TROVE_HOSTNAME  -- Upstream trove's hostname"
  echo "  VM_USER                  -- User on VM host for VM deployment"
  echo "  VM_HOST                  -- VM host for VM deployment"
  echo "  VM_PATH                  -- Path to store VM images in on VM host"
  echo "  HOST_POSTFIX             -- e.g. \".example.com\" to get"
  echo "                              my-mason-trove.example.com"
  echo ""
  echo "This script makes deploying a Mason system simpler by automating"
  echo "the generation of keys for the systems to use, building of the"
  echo "systems, filling out the mason deployment cluster morphology"
  echo "template with useful values, and finally deploying the systems."
  echo ""
  echo "To ensure that the deployed system can deploy test systems, you"
  echo "must supply an ssh key to the VM host.  Do so with the following"
  echo "command:"
  echo "  ssh-copy-id -i ssh_keys-HOST_PREFIX/mason.key.pub VM_USER@VM_HOST"
  echo ""
  exit 0
fi


HOST_PREFIX=$1
UPSTREAM_TROVE=$2
VM_USER=$3
VM_HOST=$4
VM_PATH=$5
HOST_POSTFIX=$6

sedescape() {
    # Escape all non-alphanumeric characters
    printf "%s\n" "$1" | sed -e 's/\W/\\&/g'
}


##############################################################################
# Key generation
##############################################################################

mkdir "ssh_keys-${HOST_PREFIX}"
cd "ssh_keys-${HOST_PREFIX}"
ssh-keygen -t rsa -b 2048 -f mason.key -C mason@TROVE_HOST -N ''
ssh-keygen -t rsa -b 2048 -f lorry.key -C lorry@TROVE_HOST -N ''
ssh-keygen -t rsa -b 2048 -f worker.key -C worker@TROVE_HOST -N ''
ssh-keygen -t rsa -b 2048 -f id_rsa -C trove-admin@TROVE_HOST -N ''
cd ../


##############################################################################
# Mason setup
##############################################################################

cp mason.morph mason-${HOST_PREFIX}.morph

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

morph build trove-system-x86_64
morph build distbuild-system-x86_64


##############################################################################
# System deployment
##############################################################################

morph deploy mason-${HOST_PREFIX}.morph


##############################################################################
# Cleanup
##############################################################################

rm mason-${HOST_PREFIX}.morph
