#!/usr/bin/env python

import os, re, sys, codecs

sys.path.append(sys.argv[1] + "/lib/python")

from debian_linux.config import ConfigParser, SchemaItemList
from debian_linux.debian import Package, PackageRelation
from debian_linux.debian import PackageDescription as PackageDescriptionBase
import debian_linux.gencontrol
from debian_linux.gencontrol import Makefile, MakeFlags, PackagesList
from debian_linux.utils import TextWrapper, read_control
from debian_linux.utils import Templates as TemplatesBase
from collections import OrderedDict

class PackageDescription(PackageDescriptionBase):
    __slots__ = ()

    def __init__(self, value = None):
        self.short = []
        self.long = []
        if value is not None:
            value = value.split(u"\n", 1)
            self.append_short(value[0])
            if len(value) > 1:
                self.append(value[1])

    def __unicode__(self):
        wrap = TextWrapper(width = 74, fix_sentence_endings = True).wrap
        short = u', '.join(self.short)
        long_pars = []
        for t in self.long:
            if isinstance(t, basestring):
                t = wrap(t)
            long_pars.append(u'\n '.join(t))
        long = u'\n .\n '.join(long_pars)
        return short + u'\n ' + long

    def append_pre(self, l):
        self.long.append(l)

    def extend(self, desc):
        if isinstance(desc, PackageDescription):
            self.short.extend(desc.short)
            self.long.extend(desc.long)
        elif isinstance(desc, (list, tuple)):
            for i in desc:
                self.append(i)

Package._fields['Description'] = PackageDescription

class Template(dict):
    _fields = OrderedDict((
        ('Template', unicode),
        ('Type', unicode),
        ('Default', unicode),
        ('Description', PackageDescription),
    ))

    def __setitem__(self, key, value):
        try:
            cls = self._fields[key]
            if not isinstance(value, cls):
                value = cls(value)
        except KeyError: pass
        super(Template, self).__setitem__(key, value)

    def iterkeys(self):
        keys = set(self.keys())
        for i in self._fields.iterkeys():
            if self.has_key(i):
                keys.remove(i)
                yield i
        for i in keys:
            yield i

    def iteritems(self):
        for i in self.iterkeys():
            yield (i, self[i])

    def itervalues(self):
        for i in self.iterkeys():
            yield self[i]


class Templates(TemplatesBase):
    # TODO
    def _read(self, name):
        prefix, id = name.split(u'.', 1)

        for dir in self.dirs:
            filename = "%s/%s.in" % (dir, name)
            if os.path.exists(filename):
                f = codecs.open(filename, 'r', 'utf-8')
                if prefix == 'control':
                    return read_control(f)
                elif prefix == 'templates':
                    return self._read_templates(f)
                return f.read()

    def _read_templates(self, f):
        entries = []

        while True:
            e = Template()
            last = None
            lines = []
            while True:
                line = f.readline()
                if not line:
                    break
                line = line.strip(u'\n')
                if not line:
                    break
                if line[0] in u' \t':
                    if not last:
                        raise ValueError('Continuation line seen before first header')
                    lines.append(line.lstrip())
                    continue
                if last:
                    e[last] = u'\n'.join(lines)
                i = line.find(u':')
                if i < 0:
                    raise ValueError("Not a header, not a continuation: ``%s''" % line)
                last = line[:i]
                lines = [line[i+1:].lstrip()]
            if last:
                e[last] = u'\n'.join(lines)
            if not e:
                break

            entries.append(e)

        return entries


class GenControl(debian_linux.gencontrol.Gencontrol):
    def __init__(self):
        self.config = Config()
        self.templates = Templates()

    def __call__(self):
        packages = PackagesList()
        makefile = Makefile()

        self.do_source(packages)
        self.do_meta(packages, makefile)
        self.do_main(packages, makefile)

        self.write(packages, makefile)

    def do_source(self, packages):
        source = self.templates["control.source"]
        packages['source'] = self.process_package(source[0], ())

    def do_meta(self, packages, makefile):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        for entry in self.templates["control.binary.meta"]:
            package_binary = self.process_package(entry, {})
            assert package_binary['Package'].startswith(u'firmware-')
            package = package_binary['Package'].replace(u'firmware-', u'')

            f = open('debian/copyright.meta')
            file("debian/firmware-%s.copyright" % package, 'w').write(f.read())

            makeflags = MakeFlags()
            makeflags['FILES'] = ''
            makeflags['PACKAGE'] = package
            makefile.add('binary-indep', cmds = ["$(MAKE) -f debian/rules.real binary-indep %s" % makeflags])

            packages.append(package_binary)

    def do_main(self, packages, makefile):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        makeflags = MakeFlags()

        for i in ('build', 'binary-arch', 'setup'):
            makefile.add("%s_%%" % i, cmds = ["@true"])

        for package in config_entry['packages']:
            self.do_package(packages, makefile, package, vars.copy(), makeflags.copy())

    def do_package(self, packages, makefile, package, vars, makeflags):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package

        makeflags['PACKAGE'] = package

        binary = self.templates["control.binary"]
        copyright = self.templates["copyright.binary"]

        if os.path.exists('%s/copyright' % package):
            f = open('%s/copyright' % package)
            open("debian/firmware-%s.copyright" % package, 'w').write(f.read())
        else:
            vars['license'] = codecs.open("%s/LICENSE" % package, 'r', 'utf-8').read()
            codecs.open("debian/firmware-%s.copyright" % package, 'w', 'utf-8').write(self.substitute(copyright, vars))

        try:
            os.unlink('debian/firmware-%s.bug-presubj' % package)
        except OSError:
            pass
        os.symlink('bug-presubj', 'debian/firmware-%s.bug-presubj' % package)

        files_orig = config_entry['files']
        files_real = {}
        files_unused = []
        links = {}
        links_rev = {}

        for root, dirs, files in os.walk(package):
            try:
                dirs.remove('.svn')
            except ValueError:
                pass
            for f in files:
                cur_path = root + '/' + f
                if root != package:
                    f = root[len(package) + 1 : ] + '/' + f
                if os.path.islink(cur_path):
                    if f in files_orig:
                        links[f] = os.readlink(cur_path)
                        link_target = os.path.normpath(
                            os.path.join(f, '..', links[f]))
                        links_rev.setdefault(link_target, []).append(f)
                    continue
                f1 = f.rsplit('-', 1)
                if f in files_orig:
                    files_real[f] = f, f, None
                    continue
                if len(f1) > 1:
                    f_base, f_version = f1
                    if f_base in files_orig:
                        if f_base in files_real:
                            raise RuntimeError("Multiple files for %s" % f_base)
                        files_real[f_base] = f_base, f, f_version
                        continue
                # Whitelist files not expected to be installed as firmware
                if f in ['copyright', 'defines', 'LICENSE', 'LICENSE.install',
                         'update.py', 'update.sh']:
                    continue
                files_unused.append(f)

        if files_unused:
            print >>sys.stderr, 'W: %s: unused files:' % package, \
                ' '.join(files_unused)

        makeflags['FILES'] = ' '.join(["%s:%s" % (i[1], i[0]) for i in files_real.itervalues()])
        vars['files_real'] = ' '.join(["/lib/firmware/%s" % i for i in config_entry['files']])

        makeflags['LINKS'] = ' '.join(["%s:%s" % (link, target)
                                       for link, target in links.iteritems()])

        files_desc = [u"Contents:"]

        wrap = TextWrapper(width = 71, fix_sentence_endings = True,
                           initial_indent = ' * ',
                           subsequent_indent = '   ').wrap
        for f in config_entry['files']:
            if f in links:
                continue
            f, f_real, version = files_real[f]
            c = self.config.get(('base', package, f), {})
            desc = c.get('desc')
            if version is None:
                version = c.get('version')
            try:
                f = f + u', ' + u', '.join(links_rev[f])
            except KeyError:
                pass
            if desc and version:
                desc = "%s, version %s (%s)" % (desc, version, f)
            elif desc:
                desc = u"%s (%s)" % (desc, f)
            else:
                desc = u"%s" % f
            files_desc.extend(wrap(desc))

        packages_binary = self.process_packages(binary, vars)

        packages_binary[0]['Description'].append_pre(files_desc)

        if 'initramfs-tools' in config_entry.get('support', []):
            postinst = self.templates['postinst.initramfs-tools']
            codecs.open("debian/firmware-%s.postinst" % package, 'w', 'utf-8').write(self.substitute(postinst, vars))

        if 'license-accept' in config_entry:
            license = codecs.open("%s/LICENSE.install" % package, 'r', 'utf-8').read()
            preinst = self.templates['preinst.license']
            preinst_filename = "debian/firmware-%s.preinst" % package
            codecs.open(preinst_filename, 'w', 'utf-8').write(self.substitute(preinst, vars))

            templates = self.process_templates(self.templates['templates.license'], vars)
            license_split = re.split(ur'\n\s*\n', license)
            templates[0]['Description'].extend(license_split)
            templates_filename = "debian/firmware-%s.templates" % package
            self.write_rfc822(codecs.open(templates_filename, 'w', 'utf-8'), templates)

            desc = packages_binary[0]['Description']
            desc.append(
u"""This firmware is covered by the %s.
You must agree to the terms of this license before it is installed."""
% vars['license-title'])
            packages_binary[0]['Pre-Depends'] = PackageRelation('debconf | debconf-2.0')

        packages.extend(packages_binary)

        makefile.add('binary-indep', cmds = ["$(MAKE) -f debian/rules.real binary-indep %s" % makeflags])

    def process_template(self, in_entry, vars):
        e = Template()
        for key, value in in_entry.iteritems():
            if isinstance(value, PackageDescription):
                e[key] = self.process_description(value, vars)
            elif key[:2] == 'X-':
                pass
            else:
                e[key] = self.substitute(value, vars)
        return e

    def process_templates(self, in_entries, vars):
        entries = []
        for i in in_entries:
            entries.append(self.process_template(i, vars))
        return entries

    def substitute(self, s, vars):
        if isinstance(s, (list, tuple)):
            return [self.substitute(i, vars) for i in s]
        def subst(match):
            if match.group(1):
                return vars.get(match.group(2), '')
            else:
                return vars[match.group(2)]
        return re.sub(ur'@(\??)([-_a-z]+)@', subst, unicode(s))

    def write(self, packages, makefile):
        self.write_control(packages.itervalues())
        self.write_makefile(makefile)

    def write_control(self, list):
        self.write_rfc822(codecs.open("debian/control", 'w', 'utf-8'), list)

    def write_makefile(self, makefile):
        f = codecs.open("debian/rules.gen", 'w', 'utf-8')
        makefile.write(f)
        f.close()

    def write_rfc822(self, f, list):
        for entry in list:
            for key, value in entry.iteritems():
                f.write(u"%s: %s\n" % (key, value))
            f.write(u'\n')

class Config(dict):
    config_name = "defines"

    schemas = {
        'base': {
            'files': SchemaItemList(),
            'packages': SchemaItemList(),
            'support': SchemaItemList(),
        }
    }

    def __init__(self):
        self._read_base()

    def _read_base(self):
        config = ConfigParser(self.schemas)
        config.read(self.config_name)

        packages = config['base',]['packages']

        for section in iter(config):
            real = (section[-1],) + section[:-1]
            self[real] = config[section]

        for package in packages:
            self._read_package(package)

    def _read_package(self, package):
        config = ConfigParser(self.schemas)
        config.read("%s/%s" % (package, self.config_name))

        for section in iter(config):
            if len(section) > 1:
                real = (section[-1], package, '_'.join(section[:-1]))
            else:
                real = (section[-1], package)
            s = self.get(real, {})
            s.update(config[section])
            self[real] = s

if __name__ == '__main__':
    GenControl()()
