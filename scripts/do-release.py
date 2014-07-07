# Copyright (C) 2014  Codethink Limited
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
import morphlib
import yaml

import contextlib
import gzip
import json
import logging
import os
import re
import sys
import tarfile
import urllib2


''' do-release: Baserock release tooling.

See: <http://wiki.baserock.org/guides/release-process>.

'''


class config(object):
    release_number = RELEASE NUMBER

    build_trove = 'hawkdevtrove'
    release_trove = 'git.baserock.org'

    # Note that the 'location' field of the various systems in release.morph
    # should match 'images_dir' here.
    deploy_workspace = '/src/ws-release'
    images_dir = '/src/release'
    artifacts_dir = '/src/release/artifacts'

    images_server = <YOUR USERNAME> '@download.baserock.org'
    artifacts_server = 'root@git.baserock.org'

    # These paths are passed to rsync and ssh, so relative paths will be
    # located inside the user's home directory. The artifact list file ends up
    # in the parent directory of 'artifacts_public_path'.
    images_upload_path = 'baserock-release-staging'
    images_public_path = '/srv/download.baserock.org/baserock'

    artifacts_upload_path = '/home/cache/baserock-release-staging'
    artifacts_public_path = '/home/cache/artifacts'

    # The Codethink Manchester office currently has 8Mbits/s upload available.
    # This setting ensures we use no more than half of the available bandwidth.
    bandwidth_limit_kbytes_sec = 512


def status(message, *args):
    sys.stdout.write(message % args)
    sys.stdout.write('\n')


@contextlib.contextmanager
def cwd(path):
    '''
    Context manager to set current working directory.'''
    old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def transfer(f_in, f_out, block_size=10*1024*1024, show_status=True):
    '''Stream from f_in to f_out until the end of f_in is reached.

    This function is rather like shutil.copyfileobj(), but it doesn't seem
    possible to output progress info using that function.

    '''
    total_bytes = 0
    while True:
        data = f_in.read(block_size)
        total_bytes += len(data)
        if len(data) == 0:
            break
        f_out.write(data)
        if show_status:
            sys.stdout.write(
                '\rProcessed %iMB ...' % (total_bytes / (1024 * 1024)))
            sys.stdout.flush()
    if show_status:
        sys.stdout.write('\rCompleted transfer\n')


class DeployImages(object):
    '''Stage 1: deploy release images.'''

    def create_deploy_workspace(self, path):
        '''Create or enter existing workspace for deploying release images.'''

        if not os.path.exists(path):
            status('Creating workspace %s' % path)
            cliapp.runcmd(['morph', 'init', path])
        else:
            status('Reusing existing workspace %s' % path)

        repo = 'baserock:baserock/definitions'
        branch = 'master'

        with cwd(path):
            if not os.path.exists(branch):
                status('Checking out %s branch %s' % (repo, branch))
                cliapp.runcmd(['morph', 'checkout', repo, branch])
            else:
                status('Reusing checkout of %s %s' % (repo, branch))

        definitions_dir = os.path.join(
            config.deploy_workspace, branch, 'baserock/baserock/definitions')

        return definitions_dir

    def read_morph(self, filename, kind=None):
        with open(filename) as f:
            morph = yaml.load(f)
        if kind is not None:
            assert morph['kind'] == kind
        return morph

    def deploy_single_image(self, system_name, location, version_label):
        deploy_command = [
            'morph', 'deploy', 'release.morph', system_name,
            '--trove-host=%s' % config.build_trove,
            '%s.location=%s' % (system_name, location),
            '%s.VERSION_LABEL=%s' % (system_name, version_label)
        ]

        cliapp.runcmd(deploy_command, stdout=sys.stdout)

    def deploy_images(self, release_cluster):
        '''Use `morph deploy` to create the release images.'''

        version_label = 'baserock-%s' % config.release_number
        outputs = {}

        for system in release_cluster['systems']:
            system_name = system['morph']

            if system_name not in system['deploy']:
                raise cliapp.AppException(
                    'In release.morph: system %s ID should be "%s"' %
                    (system_name, system_name))

            # The release.morph cluster must specify a basename for the file,
            # of system-name + extension. This script knows system-name, but it
            # can't find out the appropriate file extension without
            # second-guessing the behaviour of write extensions.
            basename = system['deploy'][system_name]['location']

            if '/' in basename or basename.startswith(version_label):
                raise cliapp.AppException(
                    'In release.morph: system %s.location should be just the '
                    'base name, e.g. "%s.img"' % (system_name, system_name))

            filename = '%s-%s' % (version_label, basename)
            location = os.path.join(config.images_dir, filename)

            if os.path.exists(location):
                status('Reusing existing deployment of %s', filename)
            else:
                status('Creating %s from release.morph', filename)
                self.deploy_single_image(system_name, location, version_label)

            outputs[system_name] = location

        return outputs

    def compress_images(self, outputs):
        for name, source_file in outputs.iteritems():
            target_file = source_file + '.gz'

            if os.path.exists(target_file):
                status('Reusing compressed image %s' % target_file)
            else:
                status('Compressing %s to %s', source_file, target_file)
                with open(source_file, 'r') as f_in:
                    with gzip.open(target_file, 'w', compresslevel=4) as f_out:
                        transfer(f_in, f_out)

            outputs[name] = target_file

    def run(self):
        definitions_dir = self.create_deploy_workspace(config.deploy_workspace)

        with cwd(definitions_dir):
            release_cluster = self.read_morph('release.morph', kind='cluster')
            outputs = self.deploy_images(release_cluster)

        self.compress_images(outputs)

        return outputs


class ArtifactsBundle(object):
    def __init__(self, all_artifacts, new_artifacts,
                 all_artifacts_manifest, all_artifacts_tar,
                 new_artifacts_tar):
        # Artifact basenames
        self.all_artifacts = all_artifacts
        self.new_artifacts = new_artifacts

        # Bundle files
        self.all_artifacts_manifest = all_artifacts_manifest
        self.all_artifacts_tar = all_artifacts_tar
        self.new_artifacts_tar = new_artifacts_tar


class PrepareArtifacts(object):
    '''Stage 2: Fetch all artifacts and archive them.

    This includes the system artifacts. While these are large, it's very
    helpful to have the system artifacts available in the trove.baserock.org
    artifact cache because it allows users to deploy them with `morph deploy`.
    If they are not available in the cache they must be built, which requires
    access to a system of the same architecture as the target system.

    '''

    def get_artifact_list(self, system_morphs):
        '''Return list of artifacts involved in the release.

        List is also written to a file.

        Note that this function requires the `list-artifacts` command from
        Morph of Baserock 14.23 or later.

        '''
        artifact_manifest = os.path.join(
            config.artifacts_dir, 'baserock-%s-artifacts.txt' %
            config.release_number)
        if os.path.exists(artifact_manifest):
            with open(artifact_manifest) as f:
                artifact_basenames = [line.strip() for line in f]
        else:
            text = cliapp.runcmd(
                ['morph', '--quiet', '--trove-host=%s' % config.build_trove,
                 'list-artifacts', 'baserock:baserock/definitions', 'master'] +
                system_morphs)
            artifact_basenames = text.strip().split('\n')
            with morphlib.savefile.SaveFile(artifact_manifest, 'w') as f:
                f.write(text)
        return artifact_manifest, artifact_basenames

    def query_remote_artifacts(self, trove, artifact_basenames):
        url = 'http://%s:8080/1.0/artifacts' % trove
        logging.debug('Querying %s' % url)
        f = urllib2.urlopen(url, data=json.dumps(list(artifact_basenames)))
        response = json.load(f)
        return response

    def fetch_artifact(self, remote_cache, artifact):
        f_in = remote_cache._get_file(artifact)
        artifact_local = os.path.join(config.artifacts_dir, artifact)
        with morphlib.savefile.SaveFile(artifact_local, 'wb') as f_out:
            try:
                logging.debug('Writing to %s' % artifact_local)
                transfer(f_in, f_out)
            except BaseException:
                logging.debug(
                    'Cleaning up %s after error' % artifact_local)
                f_out.abort()
                raise
        f_in.close()

    def fetch_artifacts(self, artifact_basenames):
        remote_cache = morphlib.remoteartifactcache.RemoteArtifactCache(
            'http://%s:8080' % config.build_trove)
        found_artifacts = set()

        artifacts_to_query = []
        for artifact in artifact_basenames:
            artifact_local = os.path.join(config.artifacts_dir, artifact)
            # FIXME: no checksumming of artifacts done; we could get corruption
            # introduced here and we would have no way of knowing. Cached
            # artifact validation is planned for Morph; see:
            # http://listmaster.pepperfish.net/pipermail/baserock-dev-baserock.org/2014-May/005675.html
            if os.path.exists(artifact_local):
                status('%s already cached' % artifact)
                found_artifacts.add(artifact)
            else:
                artifacts_to_query.append(artifact)

        if len(artifacts_to_query) > 0:
            result = self.query_remote_artifacts(config.build_trove,
                                                 artifacts_to_query)
            for artifact, present in result.iteritems():
                if present:
                    status('Downloading %s from remote cache' % artifact)
                    self.fetch_artifact(remote_cache, artifact)
                    found_artifacts.add(artifact)
                elif artifact.endswith('build-log'):
                    # For historical reasons, not all chunks have their
                    # build logs. Fixed here:
                    # http://git.baserock.org/cgi-bin/cgit.cgi/baserock/baserock/morph.git/commit/?id=6fb5fbad4f2876f30f482133c53f3a138911498b
                    # We still need to work around it for now, though.
                    logging.debug('Ignoring missing build log %s' % artifact)
                elif re.match('[0-9a-f]{64}\.meta', artifact):
                    # FIXME: We still don't seem to share the .meta files.
                    # We should. Note that *artifact* meta files
                    # (.stratum.meta files) can't be ignored, they are an
                    # essential part of the stratum and it's an error if
                    # such a file is missing.
                    logging.debug('Ignoring missing source metadata %s' %
                                  artifact)
                else:
                    raise cliapp.AppException(
                        'Remote artifact cache is missing artifact %s' %
                        artifact)

        return found_artifacts

    def prepare_artifacts_archive(self, tar_name, files):
        if os.path.exists(tar_name):
            status('Reusing tarball of artifacts at %s', tar_name)
        else:
            try:
                status('Creating tarball of artifacts at %s', tar_name)
                tar = tarfile.TarFile.gzopen(name=tar_name, mode='w',
                                             compresslevel=4)
                n_files = len(files)
                for i, filename in enumerate(sorted(files)):
                    logging.debug('Add %s to tar file' % filename)
                    tar.add(filename, arcname=os.path.basename(filename))
                    sys.stdout.write('\rAdded %i files of %i' % (i, n_files))
                    sys.stdout.flush()
                sys.stdout.write('\rFinished creating %s\n' % tar_name)
                tar.close()
            except BaseException:
                logging.debug('Cleaning up %s after error' % tar_name)
                os.unlink(tar_name)
                raise

    def run(self, system_morphs):
        if not os.path.exists(config.artifacts_dir):
            os.makedirs(config.artifacts_dir)

        artifact_manifest, all_artifacts = \
            self.get_artifact_list(system_morphs)

        found_artifacts = self.fetch_artifacts(all_artifacts)

        # Prepare a tar of all artifacts
        tar_name = 'baserock-%s-artifacts.tar.gz' % config.release_number
        artifacts_tar_file = os.path.join(config.artifacts_dir, tar_name)
        artifact_files = [
            os.path.join(config.artifacts_dir, a) for a in found_artifacts]

        self.prepare_artifacts_archive(artifacts_tar_file, artifact_files)

        # Also make a tar of just the artifacts that the target Trove doesn't
        # already have.
        tar_name = 'baserock-%s-new-artifacts.tar.gz' % config.release_number
        new_artifacts_tar_file = os.path.join(config.artifacts_dir, tar_name)
        result = self.query_remote_artifacts(config.release_trove,
                                             found_artifacts)
        new_artifacts = [a for a, present in result.iteritems() if not present]

        artifact_is_system = lambda name: name.split('.')[1] == 'system'
        new_artifacts = [a for a in new_artifacts if not artifact_is_system(a)]

        new_artifact_files = [
            os.path.join(config.artifacts_dir, a) for a in new_artifacts]

        self.prepare_artifacts_archive(new_artifacts_tar_file,
                                       new_artifact_files)

        return ArtifactsBundle(
            all_artifacts=found_artifacts,
            new_artifacts=new_artifacts,
            all_artifacts_manifest=artifact_manifest,
            all_artifacts_tar=artifacts_tar_file,
            new_artifacts_tar=new_artifacts_tar_file,
        )


class Upload(object):
    '''Stage 3: upload images and artifacts to public servers.

    The files are not uploaded straight to the public directories, because
    this could lead to partially uploaded artifacts being downloaded by eager
    users.

    '''

    def run_rsync(self, sources, target_server, target_path):
        target = '%s:%s' % (target_server, target_path)
        if isinstance(sources, str):
            sources = [sources]
        settings = [
            '--bwlimit=%s' % config.bandwidth_limit_kbytes_sec,
            '--partial',
            '--progress',
        ]
        cliapp.runcmd(
            ['rsync'] + settings + sources + [target], stdout=sys.stdout)

    def extract_remote_tar(self, server, filename, target_dir):
        extract_command = \
            ['tar', '-x', '-C', target_dir, '-f', filename]
        cliapp.ssh_runcmd(server, extract_command)

    def upload_release_images(self, images):
        status('Uploading images to %s', config.images_server)
        self.run_rsync(images, config.images_server, config.images_upload_path)

    def upload_artifacts(self, bundle):
        server = config.artifacts_server
        path = config.artifacts_upload_path
        files = [bundle.all_artifacts_manifest, bundle.new_artifacts_tar]

        status('Uploading new artifacts to %s', server)
        self.run_rsync(files, server, path)

        remote_artifacts_tar = self.path_relocate(
            config.artifacts_upload_path, bundle.new_artifacts_tar)

        status('Extracting %s:%s', server, remote_artifacts_tar)
        self.extract_remote_tar(server, remote_artifacts_tar, path)

    def move_files_into_public_location(self, server, remote_files,
                                        remote_target_dir, mode=None,
                                        owner=None):
        '''Move files into a public location on a remote system.

        It'd be nice to do this using install(1) but that copies the files
        rather than moving them. Since the target is accessible over the
        internet, the operation must be atomic so that users will not see
        partially-copied files.

        This function is used to copy large lists of artifact files, so it
        supports a simple batching mechanism to avoid hitting ARG_MAX. It'd
        be a better solution to extend morph-cache-server to allow receiving
        the artifacts. This would require adding some kind of authentication to
        its API, though. Note that using xargs and sending the list of files
        over stdin isn't a perfect solution (although perhaps better than the
        current one) because Busybox's 'mv' doesn't support the '-t' option,
        making it very awkward to use with 'xargs'.

        '''

        def batch(iterable, batch_size):
            '''Split an iterable up into batches of 'batch_size' items.'''
            result = []
            for item in iterable:
                result.append(item)
                if len(result) >= batch_size:
                    yield result
                    result = []
            yield result

        cliapp.ssh_runcmd(server, ['mkdir', '-p', remote_target_dir])
        for file_batch in batch(remote_files, 1024):
            if mode is not None:
                cliapp.ssh_runcmd(server, ['chmod', mode] + file_batch)
            if owner is not None:
                cliapp.ssh_runcmd(server, ['chown', owner] + file_batch)
            cliapp.ssh_runcmd(
                server, ['mv'] + file_batch + [remote_target_dir])

    def path_relocate(self, new_parent, path):
        return os.path.join(new_parent, os.path.basename(path))

    def parent_dir(self, path):
        return os.path.dirname(path.rstrip('/'))

    def make_images_public(self, image_files):
        server = config.images_server
        upload_dir = config.images_upload_path
        files = [self.path_relocate(upload_dir, f) for f in image_files]
        target_dir = config.images_public_path

        status('Moving images into %s:%s', server, target_dir)
        self.move_files_into_public_location(
            server, files, target_dir, mode='644')

    def make_artifacts_public(self, bundle):
        server = config.artifacts_server
        upload_dir = config.artifacts_upload_path
        files = [
            self.path_relocate(upload_dir, a) for a in bundle.new_artifacts]
        target = config.artifacts_public_path

        status('Moving artifacts into %s:%s', server, target)
        self.move_files_into_public_location(
            server, files, target, mode='644', owner='cache:cache')

        manifest_file = self.path_relocate(
            config.artifacts_upload_path, bundle.all_artifacts_manifest)
        self.move_files_into_public_location(
            server, [manifest_file], self.parent_dir(target), mode='644')

    def remove_intermediate_files(self, bundle):
        server = config.artifacts_server
        remote_artifacts_tar = self.path_relocate(
            config.artifacts_upload_path, bundle.new_artifacts_tar)

        status('Removing %s:%s', server, remote_artifacts_tar)
        cliapp.ssh_runcmd(server, ['rm', remote_artifacts_tar])


def check_ssh_access(server):
    status('Checking for access to server %s', server)

    try:
        cliapp.ssh_runcmd(server, ['true'])
    except cliapp.AppException as e:
        logging.debug('Got exception: %s', e)
        raise cliapp.AppException(
            'Couldn\'t connect to configured remote server %s' % server)


def main():
    logging.basicConfig(level=logging.INFO)

    check_ssh_access(config.images_server)
    check_ssh_access(config.artifacts_server)

    deploy_images = DeployImages()
    outputs = deploy_images.run()

    system_names = outputs.keys()
    image_files = outputs.values()

    prepare_artifacts = PrepareArtifacts()
    artifacts_bundle = prepare_artifacts.run(system_names)

    upload = Upload()
    upload.upload_release_images(image_files)
    upload.upload_artifacts(artifacts_bundle)

    upload.make_images_public(image_files)
    upload.make_artifacts_public(artifacts_bundle)

    upload.remove_intermediate_files(artifacts_bundle)

    status('Images uploaded to %s:%s',
           config.images_server, config.images_public_path)
    status('Artifacts uploaded to %s:%s',
           config.artifacts_server, config.artifacts_public_path)


main()
