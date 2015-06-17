#!/bin/bash
#
# Copyright ©2015  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#


# This script creates an public image in the admin tenant and
# sets tempest.conf variables for running tests with images involved.
# This is the minimal configuration to run tests for compute (api and services
# tests).
#
# NOTE: the test image will be the following cirros image:
# http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img
#


set -e

# Global variables
admin_filename="admin_env"
admin_test_image="cirros64_img_ref"
image_ref=""

# Openstack admin credentials
admin_username="admin"
admin_password="veryinsecure"
admin_tenant="admin"

# Create a file with the environment variables
# required for setting a Openstack admin user in the
# admin tenant.
create_admin_user_env(){
  cat > "$admin_filename" <<EOF
  export OS_USERNAME="$admin_username"
  export OS_PASSWORD="$admin_password"
  export OS_TENANT_NAME="$admin_tenant"
  export OS_AUTH_URL=http://$(hostname):35357/v2.0
EOF
}

# Set the image fields in tempest.conf with the UUID of the admin_test_image.
configure_image_ref(){
  image_ref="$(glance image-list | grep "$admin_test_image" | tr -d [:space:] | cut -d'|' -f 2)"
  if [ -z "image_ref" ]; then
    echo "ERROR: image_ref is empty, please check that $admin_test_image is in the image list."
    exit 1
  fi
  # Configure the UUID (image_ref) for the created image
  sed -r -i "s/[#]?image_ref =.*/image_ref = $image_ref/" tempest.conf
  # Configure image_ssh_user for the created image
  sed -r -i "s/[#]?image_ssh_user =.*/image_ssh_user = cirros/" tempest.conf
  # Configure image_ssh_password for the created image
  sed -r -i "s/[#]?image_ssh_password =.*/image_ssh_password = 'cubswin:)'/" tempest.conf
  # Configure the UUID (image_ref_alt) for the created image
  sed -r -i "s/[#]?image_ref_alt =.*/image_ref_alt = $image_ref/" tempest.conf
  # Configure image_alt_ssh_user for the created image
  sed -r -i "s/[#]?image_alt_ssh_user =.*/image_alt_ssh_user = cirros/" tempest.conf
}

create_image_for_user(){
# Create a image in the tenant $user called
  local user_name="$1"
  local test_image="$2"

  # Set the credential for $user
  source "${user_name}_env"
  # If there is an image with the same name as $test image, remove it.
  if [ $(glance image-list | grep "$test_image" | wc -l) -gt 0 ]; then
    declare -a previous_img=$(glance image-list | grep "$test_image" | awk -F "|" '{ print $2 }')
    for index in ${previous_img[@]}; do
      glance image-delete "$index"
    done
  fi
  glance image-create --name "$test_image" \
    --location http://download.cirros-cloud.net/0.3.3/cirros-0.3.3-x86_64-disk.img \
    --is-public true --disk-format qcow2 --container-format bare --progress
  if [[ $? -eq 0 ]] \
     || [[ "$(glance image-list | grep "$test_image" | wc -l)" == "1" ]]; then
    configure_image_ref
  else
    echo "ERROR: glance image-create failed."
    exit 1
  fi
}

create_tempest_custom_flavor(){
  # Set the credential for admin
  source "${admin_username}_env"
  # In order to run tests in VMs we need a alternative flavor
  # smaller than the small and bigger than the tiny flavor.
  # So we create a flavor with the following features:
  # name=m1.tempest_tests ID=6 Memory_MB=1024 Disk=1 Ephemeral=0 VCPUS=1
  echo "Creating custom small flavor for tempest tests and set it as alt_flavor in tempest.conf"
  nova flavor-create m1.tempest_tests 6 1024 1 1
  sed -r -i "s/[#]?flavor_ref_alt =.*/flavor_ref_alt = 6/" tempest.conf
}

# Configure Openstack for running tempest tests.
create_admin_user_env
create_image_for_user "$admin_username" "$admin_test_image"
create_tempest_custom_flavor
