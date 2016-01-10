#!/usr/bin/env python3

import errno, glob, os.path, re, shutil, subprocess, sys, time

sys.path.insert(0, "debian/lib/python")
rules_defs = dict((match.group(1), match.group(2))
                  for line in open('debian/rules.defs')
                  for match in [re.match(r'(\w+)\s*:=\s*(.*)\n', line)])
sys.path.append('/usr/share/linux-support-%s/lib/python' %
                rules_defs['KERNELVERSION'])
from debian_linux.firmware import FirmwareWhence
from debian_linux.debian import Changelog
from config import Config

class Main(object):
    def __init__(self, repo, commit):
        self.log = sys.stdout.write

        changelog = Changelog()[0]
        source = changelog.source
        version = changelog.version

        self.config = Config()

        self.log('Using source name %s, version %s\n' % (source, version.upstream))

        self.orig = '%s-%s' % (source, version.upstream)
        self.orig_tar = '%s_%s.orig.tar.xz' % (source, version.upstream)
        self.repo = repo
        self.commit = commit

    def __call__(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix='genorig', dir='debian')
        old_umask = os.umask(0o022)
        try:
            self.upstream_export()

            # delete_excluded() will change dir mtimes.  Capture the
            # original release time so we can apply it to the final
            # tarball.  Note this doesn't work in case we apply an
            # upstream patch, as that doesn't carry a release time.
            orig_date = time.strftime(
                "%a, %d %b %Y %H:%M:%S +0000",
                time.gmtime(
                    os.stat(os.path.join(self.dir, self.orig, 'Makefile'))
                    .st_mtime))

            self.delete_excluded()
            os.umask(old_umask)
            self.tar(orig_date)
        finally:
            os.umask(old_umask)
            shutil.rmtree(self.dir)

    def upstream_export(self):
        self.log("Exporting %s from %s\n" % (self.commit, self.repo))

        archive_proc = subprocess.Popen(['git', 'archive', '--format=tar',
                                         '--prefix=%s/' % self.orig,
                                         self.commit],
                                        cwd=self.repo,
                                        stdout=subprocess.PIPE)
        extract_proc = subprocess.Popen(['tar', '-xaf', '-'], cwd=self.dir,
                                        stdin=archive_proc.stdout)

        ret1 = archive_proc.wait()
        ret2 = extract_proc.wait()
        if ret1 or ret2:
            raise RuntimeError("Can't create archive")

    def delete_excluded(self):
        for exclusion in self.config['upstream',]['exclude']:
            for f in glob.glob(os.path.join(self.dir, self.orig, exclusion)):
                os.remove(f)

    def tar(self, orig_date):
        out = os.path.join("../orig", self.orig_tar)
        try:
            os.mkdir("../orig")
        except OSError:
            pass
        try:
            os.stat(out)
            raise RuntimeError("Destination already exists")
        except OSError:
            pass
        self.log("Generate tarball %s\n" % out)
        cmdline = '''(cd '%s' && find '%s' -print0) |
                     LC_ALL=C sort -z |
                     tar -C '%s' --no-recursion --null -T - --mtime '%s' --owner root --group root -caf '%s'
                  ''' % (self.dir, self.orig, self.dir, orig_date, out)
        try:
            if os.spawnv(os.P_WAIT, '/bin/sh', ['sh', '-c', cmdline]):
                raise RuntimeError("Can't generate tarball")
            os.chmod(out, 0o644)
        except:
            try:
                os.unlink(out)
            except OSError:
                pass
            raise
        try:
            os.symlink(os.path.join('orig', self.orig_tar), os.path.join('..', self.orig_tar))
        except OSError:
            pass

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser(usage="%prog [OPTION]... REPO")
    parser.add_option("--commit", dest="commit",
                      help="set commit, branch or tag to use (default: master)",
                      metavar="COMMIT", default='master')
    options, args = parser.parse_args()

    assert len(args) == 1
    Main(args[0], options.commit)()
