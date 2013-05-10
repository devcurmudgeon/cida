# Copyright (C) 2012-2013  Codethink Limited
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
import sys
import time
import tempfile


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
    
    def create_local_system(self, temp_root, raw_disk):
        '''Create a raw system image locally.'''
        
        size = self.get_disk_size()
        self.create_raw_disk_image(raw_disk, size)
        try:
            self.mkfs_btrfs(raw_disk)
            mp = self.mount(raw_disk)
        except BaseException:
            sys.stderr.write('Error creating disk image')
            os.remove(raw_disk)
            raise
        try:
            version_label = 'version1'
            version_root = os.path.join(mp, 'systems', version_label)
            os.makedirs(version_root)
            self.create_state(mp)
            self.create_orig(version_root, temp_root)
            self.create_fstab(version_root)
            self.create_run(version_root)
            if self.bootloader_is_wanted():
                self.install_kernel(version_root, temp_root)
                self.install_extlinux(mp)
        except BaseException, e:
            sys.stderr.write('Error creating disk image')
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
        bytes = self._parse_size(size)
        if bytes is None:
            raise morphlib.Error('Cannot parse %s value %s' % (env_var, size))
        return bytes

    def get_disk_size(self):
        '''Parse disk size from environment.'''
        return self._parse_size_from_environment('DISK_SIZE', '1G')

    def get_ram_size(self):
        '''Parse RAM size from environment.'''
        return self._parse_size_from_environment('RAM_SIZE', '1G')

    def create_state(self, real_root):
        '''Create the state subvolumes that are shared between versions'''

        self.status(msg='Creating state subvolumes')
        os.mkdir(os.path.join(real_root, 'state'))
        statedirs = ['home', 'opt', 'srv']
        for statedir in statedirs:
            dirpath = os.path.join(real_root, 'state', statedir)
            cliapp.runcmd(['btrfs', 'subvolume', 'create', dirpath])

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

    def create_fstab(self, version_root):
        '''Create an fstab.'''

        self.status(msg='Creating fstab')
        fstab = os.path.join(version_root, 'orig', 'etc', 'fstab')

        if os.path.exists(fstab):
            with open(fstab, 'r') as f:
                contents = f.read()
        else:
            contents = ''

        got_root = False
        for line in contents.splitlines():
            words = line.split()
            if len(words) >= 2 and not words[0].startswith('#'):
                got_root = got_root or words[1] == '/'

        if not got_root:
            contents += '\n/dev/sda  /  btrfs defaults,rw,noatime 0 1\n'

        with open(fstab, 'w') as f:
            f.write(contents)

    def install_kernel(self, version_root, temp_root):
        '''Install the kernel outside of 'orig' or 'run' subvolumes'''

        self.status(msg='Installing kernel')
        image_names = ['vmlinuz', 'zImage', 'uImage']
        kernel_dest = os.path.join(version_root, 'linux')
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
            f.write('kernel /systems/version1/linux\n')
            f.write('append root=/dev/sda '
                    'rootflags=subvol=systems/version1/run '
                    'init=/sbin/init rw\n')

        self.status(msg='Installing extlinux')
        cliapp.runcmd(['extlinux', '--install', real_root])

        # FIXME this hack seems to be necessary to let extlinux finish
        cliapp.runcmd(['sync'])
        time.sleep(2)

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
