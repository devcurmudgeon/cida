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

    # These locations should be appropriate 'staging' directories on the public
    # servers that host images and artifacts. Remember not to upload to the
    # public directories directly, or you risk exposing partially uploaded
    # files. Once everything has uploaded you can 'mv' the release artifacts
    # to the public directories in one quick operation.
    # FIXME: we should probably warn if the dir exists and is not empty.
    images_upload_location = \
        <YOUR USERNAME> '@download.baserock.org:baserock-release-staging'
    artifacts_upload_location = \
        'root@git.baserock.org:/home/cache/baserock-release-staging'

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

    def parse_release_cluster(self, release_cluster):
        '''Validate release cluster and list the systems being released.

        This function returns a dict mapping the system name to the location
        of its deployed image.

        It's an open question how we should detect and handle the case where a
        write extension creates more than one file. ARM kernels and GENIVI
        manifest files are possible examples of this.

        '''

        version_label = 'baserock-%s' % config.release_number

        outputs = {}
        for system in release_cluster['systems']:
            system_morph = system['morph']

            if 'release' not in system['deploy']:
                raise cliapp.AppException(
                    'In release.morph: system %s ID should be "release"' %
                    system_morph)

            # We can't override 'location' with a different value. We must use
            # what's already in the morphology, and check that it makes sense.
            location = system['deploy']['release']['location']
            if not os.path.samefile(os.path.dirname(location),
                                    config.images_dir):
                raise cliapp.AppException(
                    'In release.morph: system location %s is not inside '
                    'configured images_dir %s' % (location, config.images_dir))
            if not os.path.basename(location).startswith(version_label):
                raise cliapp.AppException(
                    'In release.morph: system image name %s does not start '
                    'with version label %s' % (location, version_label))

            outputs[system_morph] = location

        return outputs

    def deploy_images(self, outputs):
        '''Use `morph deploy` to create the release images.'''

        # FIXME: once `morph deploy` supports partial deployment, this should
        # deploy only the images which aren't already deployed... it should
        # also check if they need redeploying based on the SHA1 they were
        # deployed from, perhaps. That's getting fancy!

        todo = [f for f in outputs.itervalues() if not os.path.exists(f)]

        if len(todo) == 0:
            status('Reusing existing release images')
        else:
            logging.debug('Need to deploy images: %s' % ', '.join(todo))
            status('Creating release images from release.morph')

            version_label = 'baserock-%s' % config.release_number

            morph_config = ['--trove-host=%s' % config.build_trove]
            deploy_config = ['release.VERSION_LABEL=%s' % version_label]

            cliapp.runcmd(
                ['morph', 'deploy', 'release.morph'] + morph_config +
                deploy_config, stdout=sys.stdout)

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

        outputs = self.parse_release_cluster(release_cluster)

        with cwd(definitions_dir):
            self.deploy_images(outputs)

        self.compress_images(outputs)

        return outputs


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
        artifact_list_file = os.path.join(
            config.artifacts_dir, 'baserock-%s-artifacts.txt' %
            config.release_number)
        if os.path.exists(artifact_list_file):
            with open(artifact_list_file) as f:
                artifact_basenames = [line.strip() for line in f]
        else:
            text = cliapp.runcmd(
                ['morph', '--quiet', '--trove-host=%s' % config.build_trove,
                 'list-artifacts', 'baserock:baserock/definitions', 'master'] +
                system_morphs)
            artifact_basenames = text.strip().split('\n')
            with morphlib.savefile.SaveFile(artifact_list_file, 'w') as f:
                f.write(text)
        return artifact_list_file, artifact_basenames

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

        artifact_list_file, all_artifacts = \
            self.get_artifact_list(system_morphs)

        found_artifacts = self.fetch_artifacts(all_artifacts)

        tar_name = 'baserock-%s-artifacts.tar.gz' % config.release_number
        artifacts_tar_file = os.path.join(config.artifacts_dir, tar_name)
        artifact_files = [
            os.path.join(config.artifacts_dir, a) for a in found_artifacts]

        self.prepare_artifacts_archive(artifacts_tar_file, artifact_files)

        tar_name = 'baserock-%s-new-artifacts.tar.gz' % config.release_number
        new_artifacts_tar_file = os.path.join(config.artifacts_dir, tar_name)
        result = self.query_remote_artifacts(config.release_trove,
                                             found_artifacts)
        new_artifacts = [a for a, present in result.iteritems() if not present]
        new_artifact_files = [
            os.path.join(config.artifacts_dir, a) for a in new_artifacts
            if a.split('.')[1] != 'system']

        self.prepare_artifacts_archive(new_artifacts_tar_file,
                                       new_artifact_files)

        return (artifact_list_file, artifacts_tar_file, new_artifacts_tar_file)


class Upload(object):
    '''Stage 3: upload images and artifacts to public servers.'''

    def run_rsync(self, sources, target):
        if isinstance(sources, str):
            sources = [sources]
        settings = [
            '--bwlimit=%s' % config.bandwidth_limit_kbytes_sec,
            '--partial',
            '--progress',
        ]
        cliapp.runcmd(
            ['rsync'] + settings + sources + [target], stdout=sys.stdout)

    def upload_release_images(self, images):
        self.run_rsync(images, config.images_upload_location)

    def upload_artifacts(self, artifacts_list_file, artifacts_tar_file):
        host, path = config.artifacts_upload_location.split(':', 1)

        self.run_rsync([artifacts_list_file, artifacts_tar_file],
                       config.artifacts_upload_location)

        # UGH! Perhaps morph-cache-server should grow an authorised-users-only
        # API call receive artifacts, to avoid this.
        remote_artifacts_tar = os.path.join(
            path, os.path.basename(artifacts_tar_file))
        extract_tar_cmd = 'cd "%s" && tar xf "%s" && chown cache:cache *' % \
            (path, remote_artifacts_tar)
        cliapp.ssh_runcmd(
            host, ['sh', '-c', extract_tar_cmd])


def main():
    logging.basicConfig(level=logging.DEBUG)

    deploy_images = DeployImages()
    outputs = deploy_images.run()

    prepare_artifacts = PrepareArtifacts()
    artifacts_list_file, artifacts_tar_file, new_artifacts_tar_file = \
        prepare_artifacts.run(outputs.keys())

    upload = Upload()
    upload.upload_release_images(outputs.values())
    upload.upload_artifacts(artifacts_list_file, new_artifacts_tar_file)

    sys.stdout.writelines([
        '\nPreparation for %s release complete!\n' % config.release_number,
        'Images uploaded to %s\n' % config.images_upload_location,
        'Artifacts uploaded to %s\n' % config.artifacts_upload_location
    ])


main()
