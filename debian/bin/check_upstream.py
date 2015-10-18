#!/usr/bin/env python3

import errno, filecmp, fnmatch, glob, os.path, re, sys
from enum import Enum

sys.path.insert(0, "debian/lib/python")
rules_defs = dict((match.group(1), match.group(2))
                  for line in open('debian/rules.defs')
                  for match in [re.match(r'(\w+)\s*:=\s*(.*)\n', line)])
sys.path.append('/usr/share/linux-support-%s/lib/python' %
                rules_defs['KERNELVERSION'])
from debian_linux.firmware import FirmwareWhence
from config import Config

class DistState(Enum):
    undistributable = 1
    non_free = 2
    free = 3

def is_source_available(section):
    for file_info in section.files.values():
        if not (file_info.source or file_info.binary.endswith('.cis')):
            return False
    return True

def check_section(section):
    if re.search(r'^BSD\b'
                 r'|^GPLv2 or OpenIB\.org BSD\b'
                 r'|\bPermission\s+is\s+hereby\s+granted\s+for\s+the\s+'
                 r'distribution\s+of\s+this\s+firmware\s+(?:data|image)\b'
                 r'(?!\s+as\s+part\s+of)'
                 r'|\bRedistribution\s+and\s+use\s+in(?:\s+source\s+and)?'
                 r'\s+binary\s+forms\b'
                 r'|\bPermission\s+is\s+hereby\s+granted\b[^.]+\sto'
                 r'\s+deal\s+in\s+the\s+Software\s+without'
                 r'\s+restriction\b'
                 r'|\bredistributable\s+in\s+binary\s+form\b',
                 section.licence):
        return (DistState.free if is_source_available(section)
                else DistState.non_free)
    elif re.match(r'^(?:D|Red)istributable\b', section.licence):
        return DistState.non_free
    elif re.match(r'^GPL(?:v2|\+)?\b', section.licence):
        return (DistState.free if is_source_available(section)
                else DistState.undistributable)
    else:
        # Unrecognised and probably undistributable
        return DistState.undistributable

def main(source_dir='.'):
    config = Config()
    over_dirs = ['debian/config/' + package for
                 package in config['base',]['packages']]
    exclusions = config['upstream',]['exclude']

    for section in FirmwareWhence(open(os.path.join(source_dir, 'WHENCE'))):
        if check_section(section) == DistState.non_free:
            for file_info in section.files.values():
                if not any(fnmatch.fnmatch(file_info.binary, exclusion)
                           for exclusion in exclusions):
                    update_file(source_dir, over_dirs, file_info.binary)

def update_file(source_dir, over_dirs, filename):
    source_file = os.path.join(source_dir, filename)
    for over_dir in over_dirs:
        for over_file in ([os.path.join(over_dir, filename)] +
                          glob.glob(os.path.join(over_dir, filename + '-*'))):
            if os.path.isfile(over_file):
                if not filecmp.cmp(source_file, over_file, True):
                    print('%s: changed' % filename)
                return
    if not os.path.isfile(filename):
        print('%s: could be added' % filename)
        return

if __name__ == '__main__':
    main(*sys.argv[1:])
