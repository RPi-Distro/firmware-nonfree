#!/usr/bin/env python3

import errno, filecmp, fnmatch, glob, pathlib, re, sys
from debian import deb822
from enum import Enum

from debian_firmware.firmware import FirmwareWhence
from debian_firmware.config import Config, pattern_to_re

class DistState(Enum):
    undistributable = 1
    non_free = 2
    free = 3

def is_source_available(section):
    for file_info in section.files.values():
        if not (file_info.source
                or file_info.binary.endswith('.txt')
                or file_info.binary.endswith('.cis')):
            return False
    return True

def check_section(section):
    if section.licence is None:
        # Maybe undistributable
        return DistState.undistributable
    elif re.search(r'^BSD\b'
                   r'|^GPLv2 or OpenIB\.org BSD\b'
                   r'|^Apache-2\.0\b'
                   r'|^MIT\b'
                   r'|\bPermission\s+is\s+hereby\s+granted\s+for\s+the\s+'
                   r'distribution\s+of\s+this\s+firmware\s+(?:data|image)\b'
                   r'(?!\s+as\s+part\s+of)'
                   r'|\bRedistribution\s+and\s+use\s+in(?:\s+source\s+and)?'
                   r'\s+binary\s+forms\b'
                   r'|\bPermission\s+is\s+hereby\s+granted\b[^.]+\sto'
                   r'\s+deal\s+in\s+the\s+Software\s+without'
                   r'\s+restriction\b'
                   r'|\bredistributable\s+in\s+binary\s+form\b'
                   r'|\bgrants\s+permission\s+to\s+use\s+and\s+redistribute'
                   r'\s+these\s+firmware\s+files\b',
                   section.licence):
        return (DistState.free if is_source_available(section)
                else DistState.non_free)
    elif re.match(r'^(?:D|Red)istributable\b', section.licence):
        return DistState.non_free
    elif re.match(r'^GPL(?:v[23]|\+)?\b|^Dual GPL(?:v[23])?/', section.licence):
        return (DistState.free if is_source_available(section)
                else DistState.undistributable)
    else:
        # Unrecognised and probably undistributable
        return DistState.undistributable

def main(source_dir='.'):
    source_path = pathlib.Path(source_dir)
    added_path = pathlib.Path('debian/added-firmware')

    config = Config.read()
    with open("debian/copyright") as f:
        exclusions = deb822.Deb822(f).get("Files-Excluded", '').strip().split()
    link_exclusions = config.base.links_excluded
    unpackaged = config.base.files_unpackaged

    package_file_res = []
    for config_entry in config.package:
        package = config_entry.name
        package_file_res.append(
            ([pattern_to_re(pattern)
              for pattern in config_entry.files],
             [pattern_to_re(pattern)
              for pattern in config_entry.files_excluded])
        )

    for section in FirmwareWhence((source_path / 'WHENCE').open()):
        dist_state = check_section(section)

        for file_info in section.files.values():
            # will this file be included in the source package?
            if not any(fnmatch.fnmatch(file_info.binary, exclusion)
                       for exclusion in exclusions):
                if dist_state == DistState.non_free:
                    # Will it be included in any binary package?
                    if any(
                        (any(inc_re.fullmatch(file_info.binary)
                             for inc_re in inc_res)
                         and not any(exc_re.fullmatch(file_info.binary)
                                    for exc_re in exc_res))
                        for inc_res, exc_res in package_file_res
                    ):
                        update_file(source_path, added_path, file_info.binary)
                    elif any(fnmatch.fnmatch(file_info.binary, ignore_patt)
                             for ignore_patt in unpackaged):
                        pass
                    else:
                        print('I: %s is not included in any binary package' %
                              file_info.binary)
                elif dist_state == DistState.undistributable:
                    print('W: %s appears to be undistributable' %
                          file_info.binary)

        if dist_state == DistState.non_free:
            for link, target in section.links.items():
                link_path = pathlib.Path(link)
                target_path = ((link_path.parent / target)
                               .resolve()
                               .relative_to(pathlib.Path.cwd()))
                # - Is the target a file?
                # - Have either the target or the link itself been
                #   explicitly excluded?
                # - Will the link not be included in any binary package?
                if str(target_path) in section.files \
                   and not any(fnmatch.fnmatch(str(target_path), exclusion)
                               for exclusion in exclusions) \
                   and not any(fnmatch.fnmatch(link, exclusion)
                               for exclusion in link_exclusions) \
                   and not any(
                       (any(inc_re.fullmatch(link)
                            for inc_re in inc_res)
                        and not any(exc_re.fullmatch(link)
                                    for exc_re in exc_res))
                       for inc_res, exc_res in package_file_res
                   ):
                    print(f'I: {link} symlink is not included in any binary package')

def update_file(source_path, added_path, filename):
    source_file = source_path / filename
    over_file = added_path / filename
    if over_file.is_file():
        if not filecmp.cmp(source_file, over_file, True):
            print('I: %s: changed' % filename)

if __name__ == '__main__':
    main(*sys.argv[1:])
