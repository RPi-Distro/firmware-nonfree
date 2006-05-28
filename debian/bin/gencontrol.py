#!/usr/bin/env python2.4
import sys
sys.path.append(sys.argv[1]+ "/lib/python")
import debian_linux.config
from debian_linux.debian import *
from debian_linux.utils import *

class packages_list(sorted_dict):
    def append(self, package):
        self[package['Package']] = package

    def extend(self, packages):
        for package in packages:
            self[package['Package']] = package

class gencontrol(object):
    def __init__(self):
        self.config = config_reader()
        self.templates = templates()

    def __call__(self):
        packages = packages_list()
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

        for package in iter(self.config['base',]['packages']):
            self.do_package(packages, makefile, package, vars.copy(), makeflags.copy())

    def do_package(self, packages, makefile, package, vars, makeflags):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package

        makeflags['PACKAGE'] = package

        makeflags_string = ' '.join(["%s='%s'" % i for i in makeflags.iteritems()])

        cmds_binary_indep = []
        cmds_binary_indep.append(("$(MAKE) -f debian/rules.real binary-indep %s" % makeflags_string))
        makefile.append(("binary-indep::", cmds_binary_indep))

        binary = self.templates["control.binary"]
        binary_udeb = self.templates["control.binary.udeb"]
        copyright = self.templates["copyright.binary"]
        packages_binary = self.process_packages(binary, vars)
        packages_binary_udeb = self.process_packages(binary_udeb, vars)

        vars['license'] = file("%s/LICENSE" % package).read()

        file("debian/firmware-%s.copyright" % package, 'w').write(self.substitute(copyright, vars))

        packages.extend(packages_binary)
        packages.extend(packages_binary_udeb)

    def process_relation(self, key, e, in_e, vars):
        in_dep = in_e[key]
        dep = package_relation_list()
        for in_groups in in_dep:
            groups = package_relation_group()
            for in_item in in_groups:
                item = package_relation()
                item.name = self.substitute(in_item.name, vars)
                if in_item.version is not None:
                    item.version = self.substitute(in_item.version, vars)
                item.arches = in_item.arches
                groups.append(item)
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
        e = package()
        for key, value in in_entry.iteritems():
            if isinstance(value, package_relation_list):
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

class config_reader(debian_linux.config.config_reader):
    schema = {
        'packages': debian_linux.config.schema_item_list(),
        'support': debian_linux.config.schema_item_list(),
    }

    def __init__(self):
        super(config_reader, self).__init__(['.'])
        self._read_base()

    def _read_base(self):
        files = self._get_files(self.config_name)
        config = debian_linux.config.config_parser(self.schema, files)

        packages = config['base',]['packages']

        for section in iter(config):
            real = list(section)
            if real[-1] in packages:
                real.insert(0, 'base')
            else:
                real.insert(0, real.pop())
            self[tuple(real)] = config[section]

        for package in packages:
            self._read_package(package)

    def _read_package(self, package):
        files = self._get_files("%s/%s" % (package, self.config_name))
        config = debian_linux.config.config_parser(self.schema, files)

        for section in iter(config):
            real = list(section)
            real[0:0] = [real.pop()]
            real[1:1] = [package]
            real = tuple(real)
            s = self.get(real, {})
            s.update(config[section])
            self[tuple(real)] = s

if __name__ == '__main__':
    gencontrol()()
