#!/usr/bin/env python3
"""
clipboard.py -- Read and write FileMaker fmxmlsnippets via the macOS clipboard.

FileMaker stores clipboard objects as proprietary AppleScript descriptor classes,
not as plain text. This script converts between those classes and fmxmlsnippet XML.

IMPORTANT: Do not use pbpaste/pbcopy. They corrupt multi-byte UTF-8 characters
(such as ≠ ≤ ≥ ¶) that are common in FileMaker calculations.

See agent/docs/CLIPBOARD.md for full technical background.

Usage:
    Read FM objects from clipboard, print XML to stdout:
        python agent/scripts/clipboard.py read

    Read FM objects from clipboard, save to file:
        python agent/scripts/clipboard.py read agent/sandbox/output.xml

    Write XML file to clipboard (class auto-detected from XML content):
        python agent/scripts/clipboard.py write agent/sandbox/myscript.xml

    Write XML file to clipboard with an explicit class override:
        python agent/scripts/clipboard.py write agent/sandbox/myscript.xml --class XMSC
"""

import argparse
import re
import subprocess
import sys

# FileMaker clipboard class codes
FM_CLASSES = {
    'XMSS': 'Script Steps',
    'XMSC': 'Script',
    'XML2': 'Layout Objects',
    'XMLO': 'Layout Objects (legacy)',
    'XMFD': 'Field Definition',
    'XMFN': 'Custom Function',
    'XMTB': 'Table',
    'XMVL': 'Value List',
    'XMTH': 'Theme',
}

# Map the first XML element found inside an fmxmlsnippet to its clipboard class
XML_ELEMENT_TO_CLASS = {
    'Step':           'XMSS',
    'Script':         'XMSC',
    'CustomFunction': 'XMFN',
    'Field':          'XMFD',
    'Table':          'XMTB',
    'ValueList':      'XMVL',
    'Layout':         'XML2',
    'Theme':          'XMTH',
}


def detect_clipboard_class():
    """Return the FM class code currently on the clipboard, or None."""
    class_list = ', '.join(f'\u00abclass {c}\u00bb' for c in FM_CLASSES)
    script = f"""try
    set allowed to {{{class_list}}}
    set clipboardType to item 1 of item 1 of (clipboard info) as class
    if clipboardType is in allowed then
        return clipboardType as string
    end if
    return ""
on error
    return ""
end try"""
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    cls = result.stdout.strip()
    return cls if cls else None


def detect_class_from_xml(xml_text):
    """Infer the correct FM clipboard class from the XML element content."""
    for element, cls in XML_ELEMENT_TO_CLASS.items():
        if re.search(rf'<{element}[\s>/]', xml_text):
            return cls
    return 'XMSS'  # safe default for steps-only snippets


def read_from_clipboard(output_path=None):
    """Extract FM objects from clipboard and output as formatted XML."""
    cls = detect_clipboard_class()
    if not cls:
        print('ERROR: No FileMaker objects found on clipboard.', file=sys.stderr)
        sys.exit(1)

    # Extract hex-encoded binary, decode to bytes, validate UTF-8, format XML.
    # The sed pattern strips the «data XMSS prefix and » suffix that osascript emits.
    # xmllint --format pretty-prints; it ships with macOS Xcode command line tools.
    cmd = (
        f"osascript -e '{cls} of (the clipboard)'"
        f" | sed 's/\u00abdata ....//; s/\u00bb//'"
        f" | xxd -r -p"
        f" | iconv -f UTF-8 -t UTF-8"
        f" | xmllint --format -"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'ERROR: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)

    xml = result.stdout
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml)
        print(f'Saved {cls} ({FM_CLASSES[cls]}) to {output_path}', file=sys.stderr)
    else:
        print(xml)

    return xml


def write_to_clipboard(input_path, cls=None):
    """Write an fmxmlsnippet XML file to the clipboard as FM objects."""
    with open(input_path, 'rb') as f:
        data = f.read()

    if cls is None:
        cls = detect_class_from_xml(data.decode('utf-8', errors='replace'))

    cls = cls.upper()
    if cls not in FM_CLASSES:
        print(f"ERROR: Unknown class '{cls}'. Valid options: {', '.join(FM_CLASSES)}", file=sys.stderr)
        sys.exit(1)

    hex_data = data.hex()
    # «data XMSS<hexdata>» — the AppleScript binary descriptor literal syntax
    script = f'set the clipboard to \u00abdata {cls}{hex_data}\u00bb'
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if result.returncode != 0:
        print(f'ERROR: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)

    print(f'Clipboard ready \u2192 {input_path} as {cls} ({FM_CLASSES[cls]})', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='Read/write FileMaker fmxmlsnippets via the macOS clipboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'FM class codes: {", ".join(f"{k}={v}" for k, v in FM_CLASSES.items())}'
    )
    sub = parser.add_subparsers(dest='cmd')

    rp = sub.add_parser('read', help='Read FM objects from clipboard as XML')
    rp.add_argument('output', nargs='?', help='Output file path (default: stdout)')

    wp = sub.add_parser('write', help='Write XML file to clipboard as FM objects')
    wp.add_argument('input', help='fmxmlsnippet XML file to send to clipboard')
    wp.add_argument(
        '--class', dest='cls', default=None,
        help='FM class override (default: auto-detect from XML content)'
    )

    args = parser.parse_args()

    if args.cmd == 'read':
        read_from_clipboard(args.output)
    elif args.cmd == 'write':
        write_to_clipboard(args.input, args.cls)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
