#!/usr/bin/python

import errno, filecmp, glob, os.path, re, sys
rules_defs = dict((match.group(1), match.group(2))
                  for line in file('debian/rules.defs')
                  for match in [re.match(r'(\w+)\s*:=\s*(.*)\n', line)])
sys.path.append('/usr/share/linux-support-%s/lib/python' %
                rules_defs['KERNELVERSION'])
from debian_linux.firmware import FirmwareWhence

def main(for_main, source_dir, dest_dirs):
    for section in FirmwareWhence(open(os.path.join(source_dir, 'WHENCE'))):
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
            # Suitable for main or non-free depending on source availability
            pass
        elif re.match(r'^(?:D|Red)istributable\b', section.licence):
            # Only suitable for non-free
            if for_main:
                continue
        elif re.match(r'^GPL(?:v2|\+)?\b', section.licence):
            # Only suitable for main; source must be available
            if not for_main:
                continue
        else:
            # Probably not distributable
            continue
        for file_info in section.files.values():
            if (file_info.source or file_info.binary.endswith('.cis') or
                not for_main):
                update_file(source_dir, dest_dirs, file_info.binary)

def update_file(source_dir, dest_dirs, filename):
    source_file = os.path.join(source_dir, filename)
    if not os.path.isfile(source_file):
        return
    for dest_dir in dest_dirs:
        for dest_file in ([os.path.join(dest_dir, filename)] +
                          glob.glob(os.path.join(dest_dir, filename + '-*'))):
            if os.path.isfile(dest_file):
                if not filecmp.cmp(source_file, dest_file, True):
                    print '%s: changed' % filename
                return
    print '%s: could be added' % filename

if __name__ == '__main__':
    for_main = False
    i = 1
    if len(sys.argv) > i and sys.argv[i] == '--main':
        for_main = True
        i += 1
    if len(sys.argv) < i + 2:
        print >>sys.stderr, '''\
Usage: %s [--main] <linux-firmware-dir> <dest-dir>...

Report changes or additions in linux-firmware.git that may be suitable
for inclusion in firmware-nonfree or linux-2.6.

For firmware-nonfree, specify the per-package subdirectories as
<dest-dir>...

For linux-2.6, use the '--main' option and specify the
debian/build/build-firmware/firmware directory as <dest-dir>.
''' % sys.argv[0]
        sys.exit(2)
    main(for_main, sys.argv[i], sys.argv[i + 1 :])
