# Clipboard Interaction

FileMaker does not use plain text for clipboard objects. When you copy scripts, steps, fields, custom functions, or other objects in FileMaker, they are placed on the macOS clipboard as proprietary binary descriptor classes — not as readable text. Converting between those classes and the fmxmlsnippet XML format that this project uses requires AppleScript.

**Do not use `pbpaste` or `pbcopy` for FileMaker objects.** Both tools silently corrupt multi-byte UTF-8 characters (such as `≠`, `≤`, `≥`, `¶`) that are common in FileMaker calculations.

---

## Clipboard class codes

Each FileMaker object type corresponds to a four-letter AppleScript class code:

| Code   | FileMaker object          | fmxmlsnippet element       |
|--------|---------------------------|----------------------------|
| `XMSS` | Script Steps              | `<Step>`                   |
| `XMSC` | Script                    | `<Script>`                 |
| `XML2` | Layout Objects            | `<Layout>` (v12+)          |
| `XMLO` | Layout Objects (legacy)   | `<Layout>`                 |
| `XMFD` | Field Definition          | `<Field>`                  |
| `XMFN` | Custom Function           | `<CustomFunction>`         |
| `XMTB` | Table                     | `<Table>`                  |
| `XMVL` | Value List                | `<ValueList>`              |
| `XMTH` | Theme                     | `<Theme>`                  |

This project primarily works with `XMSS` (the output format is steps-only inside `<fmxmlsnippet type="FMObjectList">`).

---

## Using clipboard.py

A Python helper script is provided at `agent/scripts/clipboard.py`. It handles both read and write directions and auto-detects the correct class code from the XML content.

Activate the virtual environment first:

```bash
source .venv/bin/activate
```

### Read: FM objects on clipboard → XML file

After copying objects in FileMaker (`⌘C`), run:

```bash
# Print to stdout
python agent/scripts/clipboard.py read

# Save directly to the sandbox
python agent/scripts/clipboard.py read agent/sandbox/myscript.xml
```

### Write: XML file → FM objects on clipboard

After generating or editing a snippet, send it to the clipboard so it can be pasted into FileMaker (`⌘V`):

```bash
# Class is auto-detected from the XML content
python agent/scripts/clipboard.py write agent/sandbox/myscript.xml

# Override the class explicitly if needed
python agent/scripts/clipboard.py write agent/sandbox/myscript.xml --class XMSC
```

Auto-detection reads the first XML element inside the fmxmlsnippet wrapper and maps it to the correct class (e.g. `<Step>` → `XMSS`, `<CustomFunction>` → `XMFN`).

---

## How it works (low-level)

Understanding the encoding helps when diagnosing issues or working outside of `clipboard.py`.

### Reading (FM → XML)

When FileMaker objects are on the clipboard, this AppleScript pipeline extracts them as formatted XML:

```applescript
-- Auto-detect the class, then extract and format the XML
try
    set allowed to {«class XMSS», «class XML2», «class XMLO», «class XMSC», «class XMFD», «class XMFN», «class XMTB», «class XMVL», «class XMTH»}
    set clipboardType to item 1 of item 1 of (clipboard info) as class
    if clipboardType is in allowed then
        set classString to clipboardType as string
        return do shell script "osascript -e '" & classString & " of (the clipboard)' | sed 's/«data ....//; s/»//' | xxd -r -p | iconv -f UTF-8 -t UTF-8 | xmllint --format -"
    end if
on error errMsg
    return "ERROR: " & errMsg
end try
```

What each stage does:

1. `osascript -e 'XMSS of (the clipboard)'` — retrieves the raw binary value as a hex-encoded AppleScript descriptor, e.g. `«data XMSS3C3F786D6C...»`
2. `sed 's/«data ....//; s/»//'` — strips the `«data XMSS` prefix and `»` suffix, leaving only the hex string
3. `xxd -r -p` — converts the hex string back to raw bytes
4. `iconv -f UTF-8 -t UTF-8` — validates and normalizes UTF-8 encoding
5. `xmllint --format -` — pretty-prints the XML (`xmllint` is included with macOS Xcode command line tools)

### Writing (XML → FM)

To place an fmxmlsnippet on the clipboard in the correct class for FileMaker to accept:

```applescript
-- Replace XMSS with the appropriate class code and hexdata with the hex-encoded XML
set the clipboard to «data XMSShexdata»
```

From the shell (replace `XMSS` and the file path as needed):

```bash
osascript -e "set the clipboard to «data XMSS$(xxd -p < agent/sandbox/myscript.xml | tr -d '\n')»"
```

`xxd -p` produces the raw hex encoding of the file bytes. The `tr -d '\n'` removes newlines so the hex is a single unbroken string.

---

## Detecting what is on the clipboard

To check whether the clipboard currently holds FileMaker objects (and which type):

```applescript
try
    set allowed to {«class XMSS», «class XML2», «class XMLO», «class XMSC», «class XMFD», «class XMFN», «class XMTB», «class XMVL», «class XMTH»}
    set clipboardType to item 1 of item 1 of (clipboard info) as class
    if clipboardType is in allowed then
        return clipboardType as string  -- returns e.g. "XMSS"
    else
        return "No FileMaker objects on clipboard"
    end if
on error
    return "Clipboard is empty or unreadable"
end try
```

---

## Reference

The approach above is derived from [FmClipTools](https://github.com/DanShockley/FmClipTools) by Daniel A. Shockley and Erik Shagdar, which provides a complete AppleScript library for FileMaker clipboard operations including batch conversion, prettifying, and class detection.
