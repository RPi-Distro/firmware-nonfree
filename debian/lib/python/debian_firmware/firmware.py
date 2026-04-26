from dataclasses import dataclass, field
import re


@dataclass
class FirmwareFile:
    binary: str
    desc: str
    source: str
    version: str


@dataclass
class FirmwareGroup:
    driver: str
    files: dict[str, FirmwareFile]
    licence: str
    links: dict[str, str]


class FirmwareWhence(list):
    _escape_re = re.compile(r'\\(.)')
    _link_sep_re = re.compile(r'\s+-> \s*')

    def __init__(self, file) -> None:
        self.read(file)

    @staticmethod
    def _unquote(name):
        if len(name) >= 3 and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]
        return name

    @staticmethod
    def _unescape(name):
        return FirmwareWhence._escape_re.sub(r'\1', name)

    def read(self, file) -> None:
        in_header = True
        driver = None
        files = {}
        licence = None
        links = {}
        binary = []
        desc = None
        source = []
        version = None

        for line in file:
            if line.startswith('----------'):
                if in_header:
                    in_header = False
                else:
                    # Finish old group
                    if driver and (files or links):
                        self.append(FirmwareGroup(driver, files, licence,
                                                  links))
                    driver = None
                    files = {}
                    licence = None
                    links = {}
                continue

            if in_header:
                continue

            if line == '\n':
                # End of field; end of file fields
                for b in binary:
                    # XXX The WHENCE file isn't yet consistent in its
                    # association of binaries and their sources and
                    # metadata.  This associates all sources and
                    # metadata in a group with each binary.
                    files[b] = FirmwareFile(b, desc, source, version)
                binary = []
                desc = None
                source = []
                version = None
                continue

            match = re.match(
                r'(Driver|(?:Raw)?File|Link|Info|Licen[cs]e|Source|Version'
                r'|Original licen[cs]e info(?:rmation)?):\s*(.*)\n',
                line)
            if match:
                # If we've seen a license for the previous group,
                # start a new group
                if licence:
                    self.append(FirmwareGroup(driver, files, licence, links))
                    files = {}
                    licence = None
                    links = {}
                keyword, value = match.group(1, 2)
                if keyword == 'Driver':
                    driver = value.split(' ')[0].lower()
                elif keyword in ['File', 'RawFile']:
                    match = re.match(r'("[^"\n]+"|\S+)(?:\s+--\s+(.*))?', value)
                    binary.append(self._unescape(self._unquote(match.group(1))))
                    desc = match.group(2)
                elif keyword == 'Link':
                    link, target = self._link_sep_re.split(value, 1)
                    links[self._unescape(link)] = self._unescape(target)
                elif keyword in ['Info', 'Version']:
                    version = value
                elif keyword == 'Source':
                    source.append(self._unquote(value))
                else:
                    licence = value
            elif licence is not None:
                licence = (licence + '\n'
                           + re.sub(r'^(?:[/ ]\*| \*/)?\s*(.*?)\s*$', r'\1',
                                    line))

        # Finish last group if non-empty
        for b in binary:
            files[b] = FirmwareFile(b, desc, source, version)
        if driver:
            self.append(FirmwareGroup(driver, files, licence, links))
