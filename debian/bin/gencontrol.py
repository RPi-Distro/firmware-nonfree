#!/usr/bin/env python2.4
import os, sys
sys.path.append(sys.argv[2]+ "/lib/python")
import debian_linux.config
from debian_linux.debian import *
from debian_linux.utils import *

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

class PackagesList(SortedDict):
    def append(self, package):
        self[package['Package']] = package

    def extend(self, packages):
        for package in packages:
            self[package['Package']] = package

class GenControl(object):
    def __init__(self, kernelversion):
        self.config = ConfigReader()
        self.templates = Templates()
        self.kernelversion = kernelversion

    def __call__(self):
        packages = PackagesList()
        makefile = []

        self.do_source(packages)
        self.do_main(packages, makefile)

        self.write_control(packages.itervalues())
        self.write_makefile(makefile)

    def do_source(self, packages):
        source = self.templates["control.source"]
        packages['source'] = self.process_package(source[0], ())

    def do_main(self, packages, makefile):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)
        makeflags = {}

        for i in ('build', 'binary-arch', 'setup', 'source'):
            makefile.append(("%s-%%:" % i, ["@true"]))

        packages['source']['Build-Depends'].append('linux-support-%s' % self.kernelversion)

        for package in iter(self.config['base',]['packages']):
            self.do_package(packages, makefile, package, vars.copy(), makeflags.copy())

    def do_package(self, packages, makefile, package, vars, makeflags):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package

        makeflags['PACKAGE'] = package

        binary = self.templates["control.binary"]
        binary_udeb = self.templates["control.binary.udeb"]
        copyright = self.templates["copyright.binary"]

        vars['license'] = file("%s/LICENSE" % package).read()

        file("debian/firmware-%s.copyright" % package, 'w').write(self.substitute(copyright, vars))

        files_orig = set(config_entry['files'])
        files = {}
        for r in os.walk(package):
            for t in r[2]:
                t1 = t.rsplit('-', 1)
                if len(t1) == 1:
                    t1.append("unknown")
                if t1[0] in files_orig:
                    if t1[0] in files:
                        raise RuntimeError("Multiple files for %s" % t1[0])
                    files[t1[0]] = t, t1[1]

        makeflags['FILES'] = ' '.join(["%s:%s" % (i[1][0], i[0]) for i in files.iteritems()])
        vars['files_real'] = ' '.join(["/lib/firmware/%s" % i for i in config_entry['files']])

        files_desc = ["Contents:"]

        for f in config_entry['files']:
            f_in, version = files[f]
            c = self.config.get(('base', package, f), {})
            desc = c.get('desc', f)
            files_desc.append(" * %s, version %s" % (desc, version))

        packages_binary = self.process_packages(binary, vars)
        packages_binary_udeb = self.process_packages(binary_udeb, vars)

        packages_binary[0]['Description'].append_pre(files_desc)

        if 'initramfs-tools' in config_entry.get('support', []):
            hook = self.templates['hook.initramfs-tools']
            hook_filename = "debian/firmware-%s.hook.initramfs-tools" % package
            file(hook_filename, 'w').write(self.substitute(hook, vars))

            postinst = self.templates['postinst.initramfs-tools']
            file("debian/firmware-%s.postinst" % package, 'w').write(self.substitute(postinst, vars))

        packages.extend(packages_binary)
        packages.extend(packages_binary_udeb)

        makeflags_string = ' '.join(["%s='%s'" % i for i in makeflags.iteritems()])

        cmds_binary_indep = []
        cmds_binary_indep.append(("$(MAKE) -f debian/rules.real binary-indep %s" % makeflags_string))
        makefile.append(("binary-indep::", cmds_binary_indep))

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
                self.process_relation(key, e, in_entry, vars)
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

    def write_control(self, list):
        self.write_rfc822(file("debian/control", 'w'), list)

    def write_makefile(self, out_list):
        out = file("debian/rules.gen", 'w')
        for item in out_list:
            if isinstance(item, (list, tuple)):
                out.write("%s\n" % item[0])
                cmd_list = item[1]
                if isinstance(cmd_list, basestring):
                    cmd_list = cmd_list.split('\n')
                for j in cmd_list:
                    out.write("\t%s\n" % j)
            else:
                out.write("%s\n" % item)

    def write_rfc822(self, f, list):
        for entry in list:
            for key, value in entry.iteritems():
                f.write("%s: %s\n" % (key, value))
            f.write('\n')

class ConfigReader(debian_linux.config.ConfigReaderCore):
    schema = {
        'files': debian_linux.config.SchemaItemList(),
        'packages': debian_linux.config.SchemaItemList(),
        'support': debian_linux.config.SchemaItemList(),
    }

    def __init__(self):
        super(ConfigReader, self).__init__(['.'])
        self._readBase()

    def _readBase(self):
        files = self.getFiles(self.config_name)
        config = debian_linux.config.ConfigParser(self.schema, files)

        packages = config['base',]['packages']

        for section in iter(config):
            real = list(section)
            if real[-1] in packages:
                real.insert(0, 'base')
            else:
                real.insert(0, real.pop())
            self[tuple(real)] = config[section]

        for package in packages:
            self._readPackage(package)

    def _readPackage(self, package):
        files = self.getFiles("%s/%s" % (package, self.config_name))
        config = debian_linux.config.ConfigParser(self.schema, files)

        self['base', package] = config['base',]

        files = config['base',].get('files', [])

        for section in iter(config):
            real = ['_'.join(section)]
            real[0:0] = ['base', package]
            self[tuple(real)] = config[section]

if __name__ == '__main__':
    GenControl(sys.argv[1])()
