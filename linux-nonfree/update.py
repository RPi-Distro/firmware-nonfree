#!/usr/bin/python

import errno, filecmp, os.path, re, sys

def main(for_main, source_dir, dest_dir):
    sections = []
    section = None
    keyword = None
    filename = None

    for line in open(os.path.join(source_dir, 'WHENCE')):
        if line.startswith('----------'):
            # New section
            section = {
                'driver': None,
                'file': {},
                'licence': None
                }
            sections.append(section)
            continue

        if not section:
            # Skip header
            continue

        if line == '\n':
            # End of field; end of file fields
            keyword = None
            filename = None
            continue

        match = re.match(
            r'(Driver|File|Info|Licen[cs]e|Source|Version):\s*(.*)\n',
            line)
        if not match:
            continue
        keyword, value = match.group(1, 2)
        if keyword == 'Driver':
            section['driver'] = value.split(' ')[0].lower()
        elif keyword == 'File':
            match = re.match(r'(\S+)\s+--\s+(.*)', value)
            if match:
                filename = match.group(1)
                section['file'][filename] = {'info': match.group(2)}
            else:
                for filename in value.strip().split():
                    section['file'][filename] = {}
        elif keyword in ['Info', 'Version']:
            section['file'][filename]['version'] = value
        elif keyword == 'Source':
            section['file'][filename]['source'] = value
        elif keyword in ['Licence', 'License']:
            match = re.match(r'(BSD'
                             r'|GPLv2(?:\+| or later| or OpenIB\.org BSD)?'
                             r'|Redistributable\.)\b',
                             value)
            if match:
                section['licence'] = match.group(1)

    for section in sections:
        if section['licence'] in ['BSD', 'GPLv2 or OpenIB.org BSD']:
            # Suitable for main or non-free depending on source availability
            pass
        elif section['licence'] == 'Redistributable':
            # Only suitable for non-free
            if for_main:
                continue
        elif section['licence']:  # others are GPLv2 or GPLv2+
            # Only suitable for main; source must be available
            if not for_main:
                continue
        else:
            # Probably not distributable
            continue
        for filename, file_info in section['file'].iteritems():
            if file_info.get('source') or not for_main:
                update_file(source_dir, dest_dir, filename)

def update_file(source_dir, dest_dir, filename):
    try:
        if not filecmp.cmp(os.path.join(source_dir, filename),
                           os.path.join(dest_dir, filename),
                           True):
            print '%s: changed' % filename
    except EnvironmentError, e:
        if e.errno == errno.ENOENT:
            if os.path.isfile(os.path.join(source_dir, filename)):
                print '%s: could be added' % filename

if __name__ == '__main__':
    for_main = False
    i = 1
    if len(sys.argv) > i and sys.argv[i] == '--main':
        for_main = True
        i += 1
    if len(sys.argv) != i + 2:
        print >>sys.stderr, '''\
Usage: ./update.py [--main] <linux-firmware-dir> <dest-dir>

Report changes or additions in linux-firmware.git that may be suitable
for inclusion in firmware-nonfree or linux-2.6.

For firmware-nonfree, specify the linux-nonfree directory as <dest-dir>.

For linux-2.6, use the '--main' option and specify the
debian/build/build-firmware/firmware directory as <dest-dir>.
'''
        sys.exit(2)
    main(for_main, sys.argv[i], sys.argv[i + 1])
