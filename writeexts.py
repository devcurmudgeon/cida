# Copyright (C) 2012-2014  Codethink Limited
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
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.


import cliapp
import logging
import os
import re
import shutil
import sys
import time
import tempfile
import errno
import stat

import morphlib


class Fstab(object):
    '''Small helper class for parsing and adding lines to /etc/fstab.'''

    # There is an existing Python helper library for editing of /etc/fstab.
    # However it is unmaintained and has an incompatible license (GPL3).
    #
    # https://code.launchpad.net/~computer-janitor-hackers/python-fstab/trunk

    def __init__(self, filepath='/etc/fstab'):
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                self.text= f.read()
        else:
            self.text = ''
        self.filepath = filepath
        self.lines_added = 0

    def get_mounts(self):
        '''Return list of mount devices and targets in /etc/fstab.

        Return value is a dict of target -> device.
        '''
        mounts = dict()
        for line in self.text.splitlines():
            words = line.split()
            if len(words) >= 2 and not words[0].startswith('#'):
                device, target = words[0:2]
                mounts[target] = device
        return mounts

    def add_line(self, line):
        '''Add a new entry to /etc/fstab.

        Lines are appended, and separated from any entries made by configure
        extensions with a comment.

        '''
        if self.lines_added == 0:
            if len(self.text) == 0 or self.text[-1] is not '\n':
                self.text += '\n'
            self.text += '# Morph default system layout\n'
        self.lines_added += 1

        self.text += line + '\n'

    def write(self):
        '''Rewrite the fstab file to include all new entries.'''
        with morphlib.savefile.SaveFile(self.filepath, 'w') as f:
            f.write(self.text)


class WriteExtension(cliapp.Application):

    '''A base class for deployment write extensions.
    
    A subclass should subclass this class, and add a
    ``process_args`` method.
    
    Note that it is not necessary to subclass this class for write
    extensions. This class is here just to collect common code for
    write extensions.
    
    '''

    def setup_logging(self):
        '''Direct all logging output to MORPH_LOG_FD, if set.

        This file descriptor is read by Morph and written into its own log
        file.

        This overrides cliapp's usual configurable logging setup.

        '''
        log_write_fd = int(os.environ.get('MORPH_LOG_FD', 0))

        if log_write_fd == 0:
            return

        formatter = logging.Formatter('%(message)s')

        handler = logging.StreamHandler(os.fdopen(log_write_fd, 'w'))
        handler.setFormatter(formatter)

        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    def log_config(self):
        with morphlib.util.hide_password_environment_variables(os.environ):
            cliapp.Application.log_config(self)

    def process_args(self, args):
        raise NotImplementedError()

    def status(self, **kwargs):
        '''Provide status output.
        
        The ``msg`` keyword argument is the actual message,
        the rest are values for fields in the message as interpolated
        by %.
        
        '''
        
        self.output.write('%s\n' % (kwargs['msg'] % kwargs))
        self.output.flush()

    def check_for_btrfs_in_deployment_host_kernel(self):
        with open('/proc/filesystems') as f:
            text = f.read()
        return '\tbtrfs\n' in text

    def require_btrfs_in_deployment_host_kernel(self):
        if not self.check_for_btrfs_in_deployment_host_kernel():
            raise cliapp.AppException(
                'Error: Btrfs is required for this deployment, but was not '
                'detected in the kernel of the machine that is running Morph.')

    def create_local_system(self, temp_root, raw_disk):
        '''Create a raw system image locally.'''
        size = self.get_disk_size()
        if not size:
            raise cliapp.AppException('DISK_SIZE is not defined')
        self.create_raw_disk_image(raw_disk, size)
        try:
            self.mkfs_btrfs(raw_disk)
            mp = self.mount(raw_disk)
        except BaseException:
            sys.stderr.write('Error creating disk image')
            os.remove(raw_disk)
            raise
        try:
            self.create_btrfs_system_layout(
                temp_root, mp, version_label='factory',
                disk_uuid=self.get_uuid(raw_disk))
        except BaseException, e:
            sys.stderr.write('Error creating Btrfs system layout')
            self.unmount(mp)
            os.remove(raw_disk)
            raise
        else:
            self.unmount(mp)

    def _parse_size(self, size):
        '''Parse a size from a string.
        
        Return size in bytes.
        
        '''

        m = re.match('^(\d+)([kmgKMG]?)$', size)
        if not m:
            return None

        factors = {
            '': 1,
            'k': 1024,
            'm': 1024**2,
            'g': 1024**3,
        }
        factor = factors[m.group(2).lower()]

        return int(m.group(1)) * factor

    def _parse_size_from_environment(self, env_var, default):
        '''Parse a size from an environment variable.'''

        size = os.environ.get(env_var, default)
        if size is None:
            return None
        bytes = self._parse_size(size)
        if bytes is None:
            raise morphlib.Error('Cannot parse %s value %s' % (env_var, size))
        return bytes

    def get_disk_size(self):
        '''Parse disk size from environment.'''
        return self._parse_size_from_environment('DISK_SIZE', None)

    def get_ram_size(self):
        '''Parse RAM size from environment.'''
        return self._parse_size_from_environment('RAM_SIZE', '1G')

    def get_vcpu_count(self):
        '''Parse the virtual cpu count from environment.'''
        return self._parse_size_from_environment('VCPUS', '1')

    def create_raw_disk_image(self, filename, size):
        '''Create a raw disk image.'''

        self.status(msg='Creating empty disk image')
        with open(filename, 'wb') as f:
            if size > 0:
                f.seek(size-1)
                f.write('\0')

    def mkfs_btrfs(self, location):
        '''Create a btrfs filesystem on the disk.'''
        self.status(msg='Creating btrfs filesystem')
        cliapp.runcmd(['mkfs.btrfs', '-f', '-L', 'baserock', location])

    def get_uuid(self, location):
        '''Get the UUID of a block device's file system.'''
        # Requires util-linux blkid; busybox one ignores options and
        # lies by exiting successfully.
        return cliapp.runcmd(['blkid', '-s', 'UUID', '-o', 'value',
                              location]).strip()
        
    def mount(self, location):
        '''Mount the filesystem so it can be tweaked.
        
        Return path to the mount point.
        The mount point is a newly created temporary directory.
        The caller must call self.unmount to unmount on the return value.
        
        '''

        self.status(msg='Mounting filesystem')        
        tempdir = tempfile.mkdtemp()
        cliapp.runcmd(['mount', '-o', 'loop', location, tempdir])
        return tempdir
        
    def unmount(self, mount_point):
        '''Unmount the filesystem mounted by self.mount.
        
        Also, remove the temporary directory.
        
        '''
        
        self.status(msg='Unmounting filesystem')
        cliapp.runcmd(['umount', mount_point])
        os.rmdir(mount_point)

    def create_btrfs_system_layout(self, temp_root, mountpoint, version_label,
                                   disk_uuid):
        '''Separate base OS versions from state using subvolumes.

        '''
        initramfs = self.find_initramfs(temp_root)
        version_root = os.path.join(mountpoint, 'systems', version_label)
        state_root = os.path.join(mountpoint, 'state')

        os.makedirs(version_root)
        os.makedirs(state_root)

        self.create_orig(version_root, temp_root)
        system_dir = os.path.join(version_root, 'orig')

        state_dirs = self.complete_fstab_for_btrfs_layout(system_dir,
                                                          disk_uuid)

        for state_dir in state_dirs:
            self.create_state_subvolume(system_dir, mountpoint, state_dir)

        self.create_run(version_root)

        os.symlink(
                version_label, os.path.join(mountpoint, 'systems', 'default'))

        if self.bootloader_config_is_wanted():
            self.install_kernel(version_root, temp_root)
            if self.get_dtb_path() != '':
                self.install_dtb(version_root, temp_root)
            self.install_syslinux_menu(mountpoint, version_root)
            if initramfs is not None:
                self.install_initramfs(initramfs, version_root)
                self.generate_bootloader_config(mountpoint, disk_uuid)
            else:
                self.generate_bootloader_config(mountpoint)
            self.install_bootloader(mountpoint)

    def create_orig(self, version_root, temp_root):
        '''Create the default "factory" system.'''

        orig = os.path.join(version_root, 'orig')

        self.status(msg='Creating orig subvolume')
        cliapp.runcmd(['btrfs', 'subvolume', 'create', orig])
        self.status(msg='Copying files to orig subvolume')
        cliapp.runcmd(['cp', '-a', temp_root + '/.', orig + '/.'])

    def create_run(self, version_root):
        '''Create the 'run' snapshot.'''

        self.status(msg='Creating run subvolume')
        orig = os.path.join(version_root, 'orig')
        run = os.path.join(version_root, 'run')
        cliapp.runcmd(
            ['btrfs', 'subvolume', 'snapshot', orig, run])

    def create_state_subvolume(self, system_dir, mountpoint, state_subdir):
        '''Create a shared state subvolume.

        We need to move any files added to the temporary rootfs by the
        configure extensions to their correct home. For example, they might
        have added keys in `/root/.ssh` which we now need to transfer to
        `/state/root/.ssh`.

        '''
        self.status(msg='Creating %s subvolume' % state_subdir)
        subvolume = os.path.join(mountpoint, 'state', state_subdir)
        cliapp.runcmd(['btrfs', 'subvolume', 'create', subvolume])
        os.chmod(subvolume, 0755)

        existing_state_dir = os.path.join(system_dir, state_subdir)
        files = []
        if os.path.exists(existing_state_dir):
            files = os.listdir(existing_state_dir)
        if len(files) > 0:
            self.status(msg='Moving existing data to %s subvolume' % subvolume)
        for filename in files:
            filepath = os.path.join(existing_state_dir, filename)
            cliapp.runcmd(['mv', filepath, subvolume])

    def complete_fstab_for_btrfs_layout(self, system_dir, rootfs_uuid=None):
        '''Fill in /etc/fstab entries for the default Btrfs disk layout.

        In the future we should move this code out of the write extension and
        in to a configure extension. To do that, though, we need some way of
        informing the configure extension what layout should be used. Right now
        a configure extension doesn't know if the system is going to end up as
        a Btrfs disk image, a tarfile or something else and so it can't come
        up with a sensible default fstab.

        Configuration extensions can already create any /etc/fstab that they
        like. This function only fills in entries that are missing, so if for
        example the user configured /home to be on a separate partition, that
        decision will be honoured and /state/home will not be created.

        '''
        shared_state_dirs = {'home', 'root', 'opt', 'srv', 'var'}

        fstab = Fstab(os.path.join(system_dir, 'etc', 'fstab'))
        existing_mounts = fstab.get_mounts()

        if '/' in existing_mounts:
            root_device = existing_mounts['/']
        else:
            root_device = (self.get_root_device() if rootfs_uuid is None else
                           'UUID=%s' % rootfs_uuid)
            fstab.add_line('%s  / btrfs defaults,rw,noatime 0 1' % root_device)

        state_dirs_to_create = set()
        for state_dir in shared_state_dirs:
            if '/' + state_dir not in existing_mounts:
                state_dirs_to_create.add(state_dir)
                state_subvol = os.path.join('/state', state_dir)
                fstab.add_line(
                        '%s  /%s  btrfs subvol=%s,defaults,rw,noatime 0 2' %
                        (root_device, state_dir, state_subvol))

        fstab.write()
        return state_dirs_to_create

    def find_initramfs(self, temp_root):
        '''Check whether the rootfs has an initramfs.

        Uses the INITRAMFS_PATH option to locate it.
        '''
        if 'INITRAMFS_PATH' in os.environ:
            initramfs = os.path.join(temp_root, os.environ['INITRAMFS_PATH'])
            if not os.path.exists(initramfs):
                raise morphlib.Error('INITRAMFS_PATH specified, '
                                     'but file does not exist')
            return initramfs
        return None

    def install_initramfs(self, initramfs_path, version_root):
        '''Install the initramfs outside of 'orig' or 'run' subvolumes.

        This is required because syslinux doesn't traverse subvolumes when
        loading the kernel or initramfs.
        '''
        self.status(msg='Installing initramfs')
        initramfs_dest = os.path.join(version_root, 'initramfs')
        cliapp.runcmd(['cp', '-a', initramfs_path, initramfs_dest])

    def install_kernel(self, version_root, temp_root):
        '''Install the kernel outside of 'orig' or 'run' subvolumes'''

        self.status(msg='Installing kernel')
        image_names = ['vmlinuz', 'zImage', 'uImage']
        kernel_dest = os.path.join(version_root, 'kernel')
        for name in image_names:
            try_path = os.path.join(temp_root, 'boot', name)
            if os.path.exists(try_path):
                cliapp.runcmd(['cp', '-a', try_path, kernel_dest])
                break

    def install_dtb(self, version_root, temp_root):
        '''Install the device tree outside of 'orig' or 'run' subvolumes'''

        self.status(msg='Installing devicetree')
        device_tree_path = self.get_dtb_path()
        dtb_dest = os.path.join(version_root, 'dtb')
        try_path = os.path.join(temp_root, device_tree_path)
        if os.path.exists(try_path):
            cliapp.runcmd(['cp', '-a', try_path, dtb_dest])
        else:
            logging.error("Failed to find device tree %s", device_tree_path)
            raise cliapp.AppException(
                'Failed to find device tree %s' % device_tree_path)

    def get_dtb_path(self):
        return os.environ.get('DTB_PATH', '')

    def get_bootloader_install(self):
        # Do we actually want to install the bootloader?
        # Set this to "none" to prevent the install
        return os.environ.get('BOOTLOADER_INSTALL', 'extlinux')

    def get_bootloader_config_format(self):
        # The config format for the bootloader,
        # if not set we default to extlinux for x86
        return os.environ.get('BOOTLOADER_CONFIG_FORMAT', 'extlinux')

    def get_extra_kernel_args(self):
        return os.environ.get('KERNEL_ARGS', '')

    def get_root_device(self):
        return os.environ.get('ROOT_DEVICE', '/dev/sda')

    def generate_bootloader_config(self, real_root, disk_uuid=None):
        '''Install extlinux on the newly created disk image.'''
        config_function_dict = {
            'extlinux': self.generate_extlinux_config,
        }

        config_type = self.get_bootloader_config_format()
        if config_type in config_function_dict:
            config_function_dict[config_type](real_root, disk_uuid)
        else:
            raise cliapp.AppException(
                'Invalid BOOTLOADER_CONFIG_FORMAT %s' % config_type)

    def generate_extlinux_config(self, real_root, disk_uuid=None):
        '''Install extlinux on the newly created disk image.'''

        self.status(msg='Creating extlinux.conf')
        config = os.path.join(real_root, 'extlinux.conf')
        kernel_args = (
            'rw ' # ro ought to work, but we don't test that regularly
            'init=/sbin/init ' # default, but it doesn't hurt to be explicit
            'rootfstype=btrfs ' # required when using initramfs, also boots
                                # faster when specified without initramfs
            'rootflags=subvol=systems/default/run ') # boot runtime subvol
        kernel_args += 'root=%s ' % (self.get_root_device()
                                     if disk_uuid is None
                                     else 'UUID=%s' % disk_uuid)
        kernel_args += self.get_extra_kernel_args()
        with open(config, 'w') as f:
            f.write('default linux\n')
            f.write('timeout 1\n')
            f.write('label linux\n')
            f.write('kernel /systems/default/kernel\n')
            if disk_uuid is not None:
                f.write('initrd /systems/default/initramfs\n')
            if self.get_dtb_path() != '':
                f.write('devicetree /systems/default/dtb\n')
            f.write('append %s\n' % kernel_args)

    def install_bootloader(self, real_root):
        install_function_dict = {
            'extlinux': self.install_bootloader_extlinux,
        }

        install_type = self.get_bootloader_install()
        if install_type in install_function_dict:
            install_function_dict[install_type](real_root)
        elif install_type != 'none':
            raise cliapp.AppException(
                'Invalid BOOTLOADER_INSTALL %s' % install_type)

    def install_bootloader_extlinux(self, real_root):
        self.status(msg='Installing extlinux')
        cliapp.runcmd(['extlinux', '--install', real_root])

        # FIXME this hack seems to be necessary to let extlinux finish
        cliapp.runcmd(['sync'])
        time.sleep(2)

    def install_syslinux_menu(self, real_root, version_root):
        '''Make syslinux/extlinux menu binary available.

        The syslinux boot menu is compiled to a file named menu.c32. Extlinux
        searches a few places for this file but it does not know to look inside
        our subvolume, so we copy it to the filesystem root.

        If the file is not available, the bootloader will still work but will
        not be able to show a menu.

        '''
        menu_file = os.path.join(version_root, 'orig',
            'usr', 'share', 'syslinux', 'menu.c32')
        if os.path.isfile(menu_file):
            self.status(msg='Copying menu.c32')
            shutil.copy(menu_file, real_root)

    def parse_attach_disks(self):
        '''Parse $ATTACH_DISKS into list of disks to attach.'''

        if 'ATTACH_DISKS' in os.environ:
            s = os.environ['ATTACH_DISKS']
            return s.split(':')
        else:
            return []

    def bootloader_config_is_wanted(self):
        '''Does the user want to generate a bootloader config?

        The user may set $BOOTLOADER_CONFIG_FORMAT to the desired
        format (u-boot or extlinux). If not set, extlinux is the
        default but will be generated on x86-32 and x86-64, but not
        otherwise.

        '''

        def is_x86(arch):
            return (arch == 'x86_64' or
                    (arch.startswith('i') and arch.endswith('86')))

        value = os.environ.get('BOOTLOADER_CONFIG_FORMAT', '')
        if value == '':
            if not is_x86(os.uname()[-1]):
                return False

        return True

    def get_environment_boolean(self, variable):
        '''Parse a yes/no boolean passed through the environment.'''

        value = os.environ.get(variable, 'no').lower()
        if value in ['no', '0', 'false']:
            return False
        elif value in ['yes', '1', 'true']:
            return True
        else:
            raise cliapp.AppException('Unexpected value for %s: %s' %
                                      (variable, value))

    def check_ssh_connectivity(self, ssh_host):
        try:
            cliapp.ssh_runcmd(ssh_host, ['true'])
        except cliapp.AppException as e:
            logging.error("Error checking SSH connectivity: %s", str(e))
            raise cliapp.AppException(
                'Unable to SSH to %s: %s' % (ssh_host, e))

    def is_device(self, location):
        try:
            st = os.stat(location)
            return stat.S_ISBLK(st.st_mode)
        except OSError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
