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
import os
import re
import shutil
import sys
import time
import tempfile

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
                temp_root, mp, version_label='factory')
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
        cliapp.runcmd(['mkfs.btrfs', '-L', 'baserock', location])
        
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

    def create_btrfs_system_layout(self, temp_root, mountpoint, version_label):
        '''Separate base OS versions from state using subvolumes.

        '''
        version_root = os.path.join(mountpoint, 'systems', version_label)
        state_root = os.path.join(mountpoint, 'state')

        os.makedirs(version_root)
        os.makedirs(state_root)

        self.create_orig(version_root, temp_root)
        system_dir = os.path.join(version_root, 'orig')

        state_dirs = self.complete_fstab_for_btrfs_layout(system_dir)

        for state_dir in state_dirs:
            self.create_state_subvolume(system_dir, mountpoint, state_dir)

        self.create_run(version_root)

        os.symlink(
                version_label, os.path.join(mountpoint, 'systems', 'default'))

        if self.bootloader_is_wanted():
            self.install_kernel(version_root, temp_root)
            self.install_syslinux_menu(mountpoint, version_root)
            self.install_extlinux(mountpoint)

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
            shutil.move(filepath, subvolume)

    def complete_fstab_for_btrfs_layout(self, system_dir):
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
            root_device = '/dev/sda'
            fstab.add_line('/dev/sda  /  btrfs defaults,rw,noatime 0 1')

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

    def install_extlinux(self, real_root):
        '''Install extlinux on the newly created disk image.'''

        self.status(msg='Creating extlinux.conf')
        config = os.path.join(real_root, 'extlinux.conf')
        with open(config, 'w') as f:
            f.write('default linux\n')
            f.write('timeout 1\n')
            f.write('label linux\n')
            f.write('kernel /systems/default/kernel\n')
            f.write('append root=/dev/sda '
                    'rootflags=subvol=systems/default/run '
                    'init=/sbin/init rw\n')

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

    def bootloader_is_wanted(self):
        '''Does the user request a bootloader?

        The user may set $BOOTLOADER to yes, no, or auto. If not
        set, auto is the default and means that the bootloader will
        be installed on x86-32 and x86-64, but not otherwise.

        '''

        def is_x86(arch):
            return (arch == 'x86_64' or
                    (arch.startswith('i') and arch.endswith('86')))

        value = os.environ.get('BOOTLOADER', 'auto')
        if value == 'auto':
            if is_x86(os.uname()[-1]):
                value = 'yes'
            else:
                value = 'no'

        return value == 'yes'

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
