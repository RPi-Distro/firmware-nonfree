#!/usr/bin/env python3

import dataclasses
import io
import itertools
import json
import locale
import os
import pathlib
import re
import sys
from typing import Iterable, Optional

sys.path.insert(0, "debian/lib/python")
locale.setlocale(locale.LC_CTYPE, "C.UTF-8")

from config import Config, pattern_to_re
from debian_linux.dataclasses_deb822 import field_deb822, read_deb822, write_deb822
from debian_linux.debian import BinaryPackage as BinaryPackageBase, PackageDescription, PackageRelation
import debian_linux.gencontrol
from debian_linux.gencontrol import MakeFlags
from debian_linux.utils import Templates as TemplatesBase


# XXX Delete after this field is added in linux-support
@dataclasses.dataclass
class BinaryPackage(BinaryPackageBase):
    homepage: 'Optional[str]' = field_deb822(
        'Homepage',
        default=None,
    )


@dataclasses.dataclass
class Template:
    template: 'str' = field_deb822('Template')
    type: 'str' = field_deb822('Type')
    default: 'Optional[str]' = field_deb822(
        'Default',
        default=None,
    )
    description: PackageDescription = field_deb822(
        'Description',
        default_factory=PackageDescription,
    )


class Templates(TemplatesBase):
    def get_control(
        self, key: str, context: dict[str, str] = {},
    ) -> Iterable[BinaryPackage]:
        return read_deb822(BinaryPackage, io.StringIO(self.get(key, context)))

    def get_templates_control(
        self, key: str, context: dict[str, str] = {}
    ) -> Iterable[Template]:
        return read_deb822(Template, io.StringIO(self.get(key, context)))


class GenControl(debian_linux.gencontrol.Gencontrol):
    def __init__(self):
        super().__init__(Config(), Templates())

        with open('debian/modinfo.json', 'r') as f:
            self.modinfo = json.load(f)

        # Make another dict keyed by firmware names
        self.firmware_modules = {}
        for name, info  in self.modinfo.items():
            for firmware_filename in info['firmware']:
                self.firmware_modules.setdefault(firmware_filename, []) \
                                     .append(name)

    def do_main(self):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        makeflags = MakeFlags()

        self.file_errors = False
        self.file_packages = {}

        for package in config_entry['packages']:
            self.do_package(package, vars.copy(), makeflags.copy())

        for canon_path, package_suffixes in self.file_packages.items():
            if len(package_suffixes) > 1:
                print(f'E: {canon_path!s} is included in multiple packages:',
                      ', '.join(f'firmware-{suffix}'
                                for suffix in package_suffixes),
                      file=sys.stderr)
                self.file_errors = True
        if self.file_errors:
            raise Exception('error(s) found in file lists')

    def do_package(self, package, vars, makeflags):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package
        vars['package_env_prefix'] = 'FIRMWARE_' + package.upper().replace('-', '_')

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

        makeflags['FILES'] = \
            ' '.join([f'"{source}":"{dest}"'
                      for dest, source in sorted(files_real.items())]) \
               .replace(',', '[comma]')
        makeflags['LINKS'] = \
            ' '.join([f'"{link}":"{target}"'
                      for link, target in sorted(links.items())]) \
               .replace(',', '[comma]')

        firmware_meta_list = []
        module_names = set()

        for canon_path in sorted(itertools.chain(files_real, links)):
            canon_name = str(canon_path)
            firmware_meta_list.append(
                self.templates.get("metainfo.xml.firmware",
                                   {'filename': canon_name}))
            for module_name in self.firmware_modules.get(canon_name, []):
                module_names.add(module_name)

        modaliases = set()
        for module_name in module_names:
            for modalias in self.modinfo[module_name]['alias']:
                modaliases.add(modalias)
        modalias_meta_list = [
            self.templates.get("metainfo.xml.modalias",
                               {'alias': alias})
            for alias in sorted(list(modaliases))
        ]

        packages_binary = list(self.templates.get_control("binary.control", vars))

        scripts = {}

        if 'initramfs-tools' in config_entry.get('support', []):
            scripts.setdefault("postinst", []).append(
                self.templates.get('postinst.initramfs-tools', vars))

        if 'license_accept' in config_entry:
            license = open("%s/LICENSE.install" % package_dir, 'r').read()
            scripts.setdefault("preinst", []).append(
                self.templates.get('preinst.license', vars))

            templates = list(self.templates.get_templates_control('templates.license', vars))
            templates[0].description.append(re.sub('\n\n', '\n.\n', license))
            templates_filename = "debian/firmware-%s.templates" % package
            write_deb822(templates, open(templates_filename, 'w'))

            desc = packages_binary[0].description
            desc.append(
"""This firmware is covered by the %s.
You must agree to the terms of this license before it is installed."""
% vars['license_title'])
            packages_binary[0].pre_depends = PackageRelation('debconf | debconf-2.0')

        if config_entry.get('usrmovemitigation', []):
            vars['files'] = ' '.join(config_entry['usrmovemitigation'])
            for script in ("preinst", "postinst"):
                script_content = self.templates.get(
                    script + '.usrmovemitigation', vars)
                scripts.setdefault(script, []).append(script_content)
            del vars['files']

        for script, script_contents in scripts.items():
            script_contents.insert(0, "#!/bin/sh\n\nset -e\n")
            script_contents.append("#DEBHELPER#\n\nexit 0\n")
            open("debian/firmware-%s.%s" % (package, script), "w").write("\n".join(script_contents))

        self.bundle.add_packages(packages_binary, (package,), makeflags)

        vars['firmware_list'] = ''.join(firmware_meta_list)
        vars['modalias_list'] = ''.join(modalias_meta_list)
        # Underscores are preferred to hyphens
        vars['package_metainfo'] = package.replace('-', '_')
        # XXX Might need to escape some characters
        open("debian/org.debian.firmware_%(package_metainfo)s.metainfo.xml"
             % vars, 'w') \
            .write(self.templates.get("metainfo.xml", vars))

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

if __name__ == '__main__':
    GenControl()()
