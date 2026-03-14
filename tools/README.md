# tools/

Back-office utilities for maintaining the TMMA Lookup app.

## extract_streets.py

Parses the Winchester Public Book List PDF and extracts the street→precinct mapping.

### Requirements

```bash
pip install pymupdf
```

### Usage

```bash
python3 tools/extract_streets.py /path/to/2024-WINCHESTER-PUBLIC-BOOK-LIST-V2.pdf --output-dir tools/output
```

### Output files

| File | Description |
|------|-------------|
| `tools/output/streets_data.json` | Complete mapping: `{streets, streetRanges, indexEntries}` |
| `tools/output/streetRanges.json` | House-number ranges for multi-precinct streets |
| `tools/output/streets_snippet.js` | JS snippet ready to paste into `data.js` |

### When to re-run

Re-run this script whenever a new edition of the Winchester Public Book List PDF is available. After running, copy the `streets` section from `streets_snippet.js` into `data.js`, replacing the existing `streets: { ... }` block.

### Notes

- **417 streets** in the 2024 edition
- **12 streets span multiple precincts**: BACON ST, CAMBRIDGE ST, CROSS ST, EATON ST, HIGHLAND AVE, LAKE ST, MAIN ST, MYSTIC VALLEY PKY, RIDGE ST, ROBINHOOD RD, SWANTON ST, WASHINGTON ST
- For multi-precinct streets, precinct boundaries don't follow simple house-number ranges (boundaries are irregular / by side of street). The app shows users all matching precincts for disambiguation.
