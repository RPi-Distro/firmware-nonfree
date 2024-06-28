#!/usr/bin/env python3

import io
import json
import locale
import os
import pathlib
import re
import sys

sys.path.insert(0, "debian/lib/python")
sys.path.append(sys.argv[1] + "/lib/python")
locale.setlocale(locale.LC_CTYPE, "C.UTF-8")

from config import Config, pattern_to_re
from debian_linux.debian import BinaryPackage, PackageRelation, _ControlFileDict
from debian_linux.debian import PackageDescription as PackageDescriptionBase
import debian_linux.gencontrol
from debian_linux.gencontrol import Makefile, MakeFlags, PackagesList
from debian_linux.utils import TextWrapper
from debian_linux.utils import Templates as TemplatesBase
from collections import OrderedDict

class PackageDescription(PackageDescriptionBase):
    __slots__ = ()

    def __init__(self, value = None):
        self.short = []
        self.long = []
        if value is not None:
            value = value.split("\n", 1)
            self.append_short(value[0])
            if len(value) > 1:
                self.append(value[1])

    def __str__(self):
        wrap = TextWrapper(width = 74, fix_sentence_endings = True).wrap
        short = ', '.join(self.short)
        long_pars = []
        for t in self.long:
            if isinstance(t, str):
                t = wrap(t)
            long_pars.append('\n '.join(t))
        long = '\n .\n '.join(long_pars)
        return short + '\n ' + long

    def append_pre(self, l):
        self.long.append(l)

    def extend(self, desc):
        if isinstance(desc, PackageDescription):
            self.short.extend(desc.short)
            self.long.extend(desc.long)
        elif isinstance(desc, (list, tuple)):
            for i in desc:
                self.append(i)

BinaryPackage._fields['Description'] = PackageDescription

class Template(_ControlFileDict):
    _fields = OrderedDict((
        ('Template', str),
        ('Type', str),
        ('Default', str),
        ('Description', PackageDescriptionBase),
    ))


class Templates(TemplatesBase):
    def get_templates_control(self, key: str, context: dict[str, str] = {}) -> Template:
        return Template.read_rfc822(io.StringIO(self.get(key, context)))


class GenControl(debian_linux.gencontrol.Gencontrol):
    def __init__(self):
        self.config = Config()
        self.templates = Templates()

        with open('debian/modinfo.json', 'r') as f:
            self.modinfo = json.load(f)

        # Make another dict keyed by firmware names
        self.firmware_modules = {}
        for name, info  in self.modinfo.items():
            for firmware_filename in info['firmware']:
                self.firmware_modules.setdefault(firmware_filename, []) \
                                     .append(name)

    def __call__(self):
        packages = PackagesList()
        makefile = Makefile()

        self.do_source(packages)
        self.do_extra(packages, makefile)

        self.file_errors = False
        self.file_packages = {}
        self.do_main(packages, makefile)
        for canon_path, package_suffixes in self.file_packages.items():
            if len(package_suffixes) > 1:
                print(f'E: {canon_path!s} is included in multiple packages:',
                      ', '.join(f'firmware-{suffix}'
                                for suffix in package_suffixes),
                      file=sys.stderr)
                self.file_errors = True
        if self.file_errors:
            raise Exception('error(s) found in file lists')

        self.write(packages, makefile)

    def do_source(self, packages):
        packages['source'] = self.templates.get_source_control("control.source", {})[0]

    def do_extra(self, packages, makefile):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        for package_binary in self.templates.get_control("control.extra", {}):
            assert package_binary['Package'].startswith('firmware-')
            package = package_binary['Package'].replace('firmware-', '')

            makeflags = MakeFlags()
            makeflags['FILES'] = ''
            makeflags['PACKAGE'] = package
            makefile.add_cmds('binary-indep', ["$(MAKE) -f debian/rules.real binary-indep %s" % makeflags])

            packages.append(package_binary)

    def do_main(self, packages, makefile):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        makeflags = MakeFlags()

        for i in ('build', 'binary-arch', 'setup'):
            makefile.add_cmds("%s_%%" % i, ["@true"])

        for package in config_entry['packages']:
            self.do_package(packages, makefile, package, vars.copy(), makeflags.copy())

    def do_package(self, packages, makefile, package, vars, makeflags):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package
        vars['package-env-prefix'] = 'FIRMWARE_' + package.upper().replace('-', '_')

        makeflags['PACKAGE'] = package

        # Those might be absent, set them to empty string for replacement to work:
        empty_list = ['replaces', 'conflicts', 'breaks', 'provides', 'recommends']
        for optional in ['replaces', 'conflicts', 'breaks', 'provides', 'recommends']:
            if optional not in vars:
                vars[optional] = ''

        cur_dir = pathlib.Path.cwd()
        install_dir = pathlib.Path('debian/build/install')
        package_dir = pathlib.Path('debian/config') / package

        try:
            os.unlink('debian/firmware-%s.bug-presubj' % package)
        except OSError:
            pass
        os.symlink('bug-presubj', 'debian/firmware-%s.bug-presubj' % package)

        files_include = [(pattern, pattern_to_re(pattern))
                         for pattern in config_entry['files']]
        files_exclude = [pattern_to_re(pattern)
                         for pattern in config_entry.get('files-excluded', [])]
        files_added = set()
        files_unused = set()
        files_real = {}
        links = {}
        links_rev = {}

        # List all additional and replacement files in binary package
        # config so we can:
        # - match dangling symlinks which pathlib.Path.glob() would ignore
        # - warn if any are unused
        for root, dir_names, file_names in os.walk(package_dir):
            root = pathlib.Path(root)
            for name in file_names:
                if not (root == package_dir \
                        and name in ['defines', 'LICENSE.install',
                                     'update.py', 'update.sh']):
                    canon_path = root.relative_to(package_dir) / name
                    files_added.add(canon_path)
                    files_unused.add(canon_path)

        for pattern, pattern_re in files_include:
            matched = False
            matched_more = False

            for paths, is_added in [
                (((canon_path, package_dir / canon_path)
                  for canon_path in files_added
                  if pattern_re.fullmatch(str(canon_path))),
                 True),
                (((cur_path.relative_to(install_dir), cur_path)
                  for cur_path in install_dir.glob(pattern)),
                 False)
            ]:
                for canon_path, cur_path in paths:
                    canon_name = str(canon_path)
                    if any(exc_pattern_re.fullmatch(canon_name)
                           for exc_pattern_re in files_exclude):
                        continue

                    matched = True

                    # Skip if already matched by earlier pattern or in
                    # other directory
                    if canon_path in files_real or canon_path in links:
                        continue

                    matched_more = True
                    if is_added:
                        files_unused.remove(canon_path)
                    if cur_path.is_symlink():
                        links[canon_path] = cur_path.readlink()
                    elif cur_path.is_file():
                        files_real[canon_path] = cur_path

                    self.file_packages.setdefault(canon_path, []) \
                                      .append(package)

            # Non-matching pattern is an error
            if not matched:
                print(f'E: {package}: {pattern} did not match anything',
                      file=sys.stderr)
                self.file_errors = True
            # Redundant pattern deserves a warning
            elif not matched_more:
                print(f'W: {package}: pattern {pattern} is redundant with earlier patterns',
                      file=sys.stderr)

        for canon_path in links:
            link_target = ((canon_path.parent / links[canon_path])
                           .resolve(strict=False)
                           .relative_to(cur_dir))
            links_rev.setdefault(link_target, []).append(canon_path)

        if files_unused:
            print(f'W: {package}: unused files:',
                  ', '.join(str(path) for path in files_unused),
                  file=sys.stderr)

        makeflags['FILES'] = ' '.join([f'"{source}":"{dest}"'
                                       for dest, source in sorted(files_real.items())])
        vars['files_real'] = ' '.join(["/lib/firmware/%s" % i for i in config_entry['files']])

        makeflags['LINKS'] = ' '.join([f'"{link}":"{target}"'
                                       for link, target in sorted(links.items())])

        files_desc = ["Contents:"]
        firmware_meta_temp = self.templates.get("metainfo.xml.firmware")
        firmware_meta_list = []
        module_names = set()

        wrap = TextWrapper(width = 71, fix_sentence_endings = True,
                           initial_indent = ' * ',
                           subsequent_indent = '   ').wrap
        for canon_path, is_link in sorted(
            [(path, False) for path in files_real]
            + [(path, True) for path in links]
        ):
            canon_name = str(canon_path)
            firmware_meta_list.append(self.substitute(firmware_meta_temp,
                                                      {'filename': canon_name}))
            for module_name in self.firmware_modules.get(canon_name, []):
                module_names.add(module_name)
            if is_link:
                continue
            cur_path = files_real[canon_path]
            c = self.config.get(('base', package, canon_name), {})
            desc = c.get('desc')
            version = c.get('version')
            try:
                canon_names = (canon_name + ', '
                               + ', '.join(str(path) for path in
                                           sorted(links_rev[canon_path])))
            except KeyError:
                canon_names = canon_name
            if desc and version:
                desc = "%s, version %s (%s)" % (desc, version, canon_names)
            elif desc:
                desc = "%s (%s)" % (desc, canon_names)
            else:
                desc = "%s" % canon_names
            files_desc.extend(wrap(desc))

        modaliases = set()
        for module_name in module_names:
            for modalias in self.modinfo[module_name]['alias']:
                modaliases.add(modalias)
        modalias_meta_list = [
            self.substitute(self.templates.get("metainfo.xml.modalias"),
                            {'alias': alias})
            for alias in sorted(list(modaliases))
        ]

        packages_binary = self.templates.get_control("control.binary", vars)

        packages_binary[0]['Description'].append_pre(files_desc)

        scripts = {}

        if 'initramfs-tools' in config_entry.get('support', []):
            postinst = self.templates.get('postinst.initramfs-tools')
            scripts.setdefault("postinst", []).append(self.substitute(postinst, vars))

        if 'license-accept' in config_entry:
            license = open("%s/LICENSE.install" % package_dir, 'r').read()
            preinst = self.templates.get('preinst.license')
            scripts.setdefault("preinst", []).append(self.substitute(preinst, vars))

            templates = self.templates.get_templates_control('templates.license', vars)
            templates[0]['Description'].append(re.sub('\n\n', '\n.\n', license))
            templates_filename = "debian/firmware-%s.templates" % package
            self.write_rfc822(open(templates_filename, 'w'), templates)

            desc = packages_binary[0]['Description']
            desc.append(
"""This firmware is covered by the %s.
You must agree to the terms of this license before it is installed."""
% vars['license-title'])
            packages_binary[0]['Pre-Depends'] = PackageRelation('debconf | debconf-2.0')

        if config_entry.get('usrmovemitigation', []):
            for script in ("preinst", "postinst"):
                script_template = self.templates.get(script + '.usrmovemitigation')
                script_content = self.substitute(script_template, dict(files=config_entry["usrmovemitigation"]))
                scripts.setdefault(script, []).append(script_content)

        for script, script_contents in scripts.items():
            script_contents.insert(0, "#!/bin/sh\n\nset -e\n")
            script_contents.append("#DEBHELPER#\n\nexit 0\n")
            open("debian/firmware-%s.%s" % (package, script), "w").write("\n".join(script_contents))

        packages.extend(packages_binary)

        makefile.add_cmds('binary-indep', ["$(MAKE) -f debian/rules.real binary-indep %s" % makeflags])

        vars['firmware-list'] = ''.join(firmware_meta_list)
        vars['modalias-list'] = ''.join(modalias_meta_list)
        # Underscores are preferred to hyphens
        vars['package-metainfo'] = package.replace('-', '_')
        # Summary must not contain line breaks
        vars['longdesc-metainfo'] = re.sub(r'\s+', ' ', vars['longdesc'])
        package_meta_temp = self.templates.get("metainfo.xml", {})
        # XXX Might need to escape some characters
        open("debian/firmware-%s.metainfo.xml" % package, 'w').write(self.substitute(package_meta_temp, vars))

    def process_template(self, in_entry, vars):
        e = Template()
        for key, value in in_entry.items():
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
        return re.sub(r'@(\??)([-_a-z]+)@', subst, str(s))

    def write(self, packages, makefile):
        self.write_control(packages.values())
        self.write_makefile(makefile)

    def write_control(self, list):
        self.write_rfc822(open("debian/control", 'w'), list)

    def write_makefile(self, makefile):
        f = open("debian/rules.gen", 'w')
        makefile.write(f)
        f.close()

    def write_rfc822(self, f, list):
        for entry in list:
            for key, value in entry.items():
                f.write("%s: %s\n" % (key, value))
            f.write('\n')

if __name__ == '__main__':
    GenControl()()
