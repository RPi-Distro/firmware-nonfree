#!/usr/bin/env python2.4

import os, re, sys

sys.path.append(sys.argv[2] + "/lib/python")

from debian_linux.config import ConfigParser, SchemaItemList
from debian_linux.debian import Package, PackageRelation
from debian_linux.gencontrol import Makefile, MakeFlags, PackagesList
from debian_linux.utils import Templates, TextWrapper

class PackageDescription(object):
    __slots__ = "short", "long"

    _wrap = TextWrapper(width = 74, fix_sentence_endings = True).wrap

    def __init__(self, value = None):
        self.long = []
        if value is not None:
            value = value.split("\n", 1)
            self.short = value[0]
            if len(value) > 1:
                self.append(value[1])
        else:
            self.short = None

    def __str__(self):
        if self.long:
            pars = []
            for  t in self.long:
                if isinstance(t, basestring):
                    t = self._wrap(t)
                pars.append('\n '.join(t))
            return self.short + '\n ' + '\n .\n '.join(pars)
        else:
            return self.short

    def append(self, str):
        str = str.strip()
        if str:
            for t in str.split("\n.\n"):
                self.long.append(t)

    def append_pre(self, l):
        self.long.append(l)

Package._fields['Description'] = PackageDescription

class GenControl(object):
    def __init__(self, kernelversion):
        self.config = Config()
        self.templates = Templates()
        self.kernelversion = kernelversion

    def __call__(self):
        packages = PackagesList()
        makefile = Makefile()

        self.do_source(packages)
        self.do_main(packages, makefile)

        self.write(packages, makefile)

    def do_source(self, packages):
        source = self.templates["control.source"]
        packages['source'] = self.process_package(source[0], ())
        packages['source']['Build-Depends'].append('linux-support-%s' % self.kernelversion)

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

        vars['license'] = file("%s/LICENSE" % package).read()

        file("debian/firmware-%s.copyright" % package, 'w').write(self.substitute(copyright, vars))

        files_orig = config_entry['files']
        files_real = {}

        for root, dirs, files in os.walk(package):
            del dirs[:]
            for f in files:
                f1  = f.rsplit('-', 1)
                if f in files_orig:
                    files_real[f] = f, f, None
                elif len(f1) > 1:
                    f_base, f_version = f1
                    if f_base in files_orig:
                        if f_base in files_real:
                            raise RuntimeError("Multiple files for %s" % f_base)
                        files_real[f_base] = f_base, f, f_version

        makeflags['FILES'] = ' '.join(["%s:%s" % (i[1], i[0]) for i in files_real.itervalues()])
        vars['files_real'] = ' '.join(["/lib/firmware/%s" % i for i in config_entry['files']])

        files_desc = ["Contents:"]

        for f in config_entry['files']:
            f, f_real, version = files_real[f]
            c = self.config.get(('base', package, f), {})
            desc = c.get('desc', f)
            if version is None:
                version = c.get('version', 'unknown')
            files_desc.append(" * %s, version %s" % (desc, version))

        packages_binary = self.process_packages(binary, vars)

        packages_binary[0]['Description'].append_pre(files_desc)

        if 'initramfs-tools' in config_entry.get('support', []):
            hook = self.templates['hook.initramfs-tools']
            hook_filename = "debian/firmware-%s.hook.initramfs-tools" % package
            file(hook_filename, 'w').write(self.substitute(hook, vars))

            postinst = self.templates['postinst.initramfs-tools']
            file("debian/firmware-%s.postinst" % package, 'w').write(self.substitute(postinst, vars))

        packages.extend(packages_binary)

        makefile.add('binary-indep', cmds = ["$(MAKE) -f debian/rules.real binary-indep %s" % makeflags])

    def process_relation(self, key, e, in_e, vars):
        in_dep = in_e[key]
        dep = PackageRelation()
        for in_groups in in_dep:
            groups = PackageRelationGroup()
            for in_item in in_groups:
                groups.append(PackageRelationEntry(str(in_item)))
            dep.append(groups)
        e[key] = dep

    def process_description(self, e, in_e, vars):
        in_desc = in_e['Description']
        desc = in_desc.__class__()
        desc.short = self.substitute(in_desc.short, vars)
        for i in in_desc.long:
            desc.long.append(self.substitute(i, vars))
        e['Description'] = desc

    def process_package(self, in_entry, vars):
        e = Package()
        for key, value in in_entry.iteritems():
            if isinstance(value, PackageRelation):
                e[key] = in_entry[key]
#                self.process_relation(key, e, in_entry, vars)
            elif key == 'Description':
                self.process_description(e, in_entry, vars)
            elif key[:2] == 'X-':
                pass
            else:
                e[key] = self.substitute(value, vars)
        return e

    def process_packages(self, in_entries, vars):
        entries = []
        for i in in_entries:
            entries.append(self.process_package(i, vars))
        return entries

    def substitute(self, s, vars):
        if isinstance(s, (list, tuple)):
            for i in xrange(len(s)):
                s[i] = self.substitute(s[i], vars)
            return s
        def subst(match):
            return vars[match.group(1)]
        return re.sub(r'@([a-z_]+)@', subst, s)

    def write(self, packages, makefile):
        self.write_control(packages.itervalues())
        self.write_makefile(makefile)

    def write_control(self, list):
        self.write_rfc822(file("debian/control", 'w'), list)

    def write_makefile(self, makefile):
        f = file("debian/rules.gen", 'w')
        makefile.write(f)
        f.close()

    def write_rfc822(self, f, list):
        for entry in list:
            for key, value in entry.iteritems():
                f.write("%s: %s\n" % (key, value))
            f.write('\n')

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
    GenControl(sys.argv[1])()
