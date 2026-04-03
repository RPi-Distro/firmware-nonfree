#!/usr/bin/env python3

import dataclasses
import io
import locale
import os
import pathlib
import re
import sys
from typing import Iterable, Optional

locale.setlocale(locale.LC_CTYPE, "C.UTF-8")

from debian_firmware.config import Config, pattern_to_re
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

    def do_source(self):
        super().do_source()

        # We don't want to generate a makefile
        self.bundle.write_makefile = lambda *_: None

    def do_main(self):
        config_entry = self.config['base',]
        vars = {}
        vars.update(config_entry)

        for package in config_entry['packages']:
            self.do_package(package, vars.copy())

    def do_package(self, package, vars):
        config_entry = self.config['base', package]
        vars.update(config_entry)
        vars['package'] = package
        vars['package_env_prefix'] = 'FIRMWARE_' + package.upper().replace('-', '_')

        # Those might be absent, set them to empty string for replacement to work:
        empty_list = ['replaces', 'conflicts', 'breaks', 'provides', 'recommends', 'depends']
        for optional in ['replaces', 'conflicts', 'breaks', 'provides', 'recommends', 'depends']:
            if optional not in vars:
                vars[optional] = ''

        package_dir = pathlib.Path('debian/config') / package

        try:
            os.unlink('debian/firmware-%s.bug-presubj' % package)
        except OSError:
            pass
        os.symlink('bug-presubj', 'debian/firmware-%s.bug-presubj' % package)

        packages_binary = list(self.templates.get_control("binary.control", vars))

        scripts = {}

        if 'initramfs-tools' in config_entry.get('support', []):
            scripts.setdefault("postinst", []).append(
                self.templates.get('postinst.initramfs-tools', vars))

        if 'license_title' in config_entry:
            with open("%s/LICENSE.install" % package_dir, 'r') as license_fh:
                license = license_fh.read()
            scripts.setdefault("preinst", []).append(
                self.templates.get('preinst.license', vars))

            templates = list(self.templates.get_templates_control('templates.license', vars))
            templates[0].description.append(re.sub('\n\n', '\n.\n', license))
            templates_filename = "debian/firmware-%s.templates" % package
            with open(templates_filename, 'w') as templates_fh:
                write_deb822(templates, templates_fh)

            desc = packages_binary[0].description
            desc.append(
"""This firmware is covered by the %s.
You must agree to the terms of this license before it is installed."""
% vars['license_title'])
            packages_binary[0].pre_depends = PackageRelation('debconf | debconf-2.0')

        for script, script_contents in scripts.items():
            script_contents.insert(0, "#!/bin/sh\n\nset -e\n")
            script_contents.append("#DEBHELPER#\n\nexit 0\n")
            with open("debian/firmware-%s.%s" % (package, script), "w") as script_fh:
                script_fh.write("\n".join(script_contents))

        self.bundle.add_packages(packages_binary, (package,), MakeFlags())


if __name__ == '__main__':
    GenControl()()
