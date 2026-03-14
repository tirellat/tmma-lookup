#!/usr/bin/env python3
"""
extract_streets.py — Winchester TMMA Street & House# Extraction Tool
======================================================================
Parses the 2024 Winchester Public Book List PDF to extract:
  1. Street Index (pages 7–10): street name → precinct(s) → book page
  2. Alphabetical List (pages 106–211): person → house# + apt + street + precinct

Outputs:
  output/streets_data.json       — streets + multi-precinct house# maps
  output/all_addresses.json      — every person record (house, apt, street, precinct)
  output/house_precincts.json    — {street: {houseNum: precinct}} for ALL streets

Usage:
  python3 extract_streets.py [PDF_PATH]

Default PDF path: ../../2024-WINCHESTER-PUBLIC-BOOK-LIST-V2.pdf (relative to this script)
"""

import fitz  # PyMuPDF
import json
import re
import sys
import os
from collections import defaultdict

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PDF = os.path.join(SCRIPT_DIR, "../../2024-WINCHESTER-PUBLIC-BOOK-LIST-V2.pdf")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

# Page ranges (0-indexed)
STREET_INDEX_PAGES = range(6, 10)       # pages 7–10
ALPHA_LIST_PAGES   = range(105, 211)    # pages 106–211

# Column x-coordinate boundaries for the Alphabetical List
# Left column
L_V      = (35,  48)
L_NAME   = (50, 150)
L_HOUSE  = (150, 175)
L_APT    = (175, 195)
L_STREET = (195, 290)
L_PCT    = (285, 300)

# Right column  
R_V      = (325, 338)
R_NAME   = (338, 438)
R_HOUSE  = (438, 463)
R_APT    = (463, 483)
R_STREET = (483, 580)
R_PCT    = (573, 588)

# Words to skip (headers / section letters)
SKIP_WORDS = {
    "TOWN", "OF", "WINCHESTER", "2024", "ALPHABETICAL", "LIST",
    "V", "NAME", "HOUSE", "APT", "STREET", "PCT",
    "A","B","C","D","E","F","G","H","I","J","K","L","M",
    "N","O","P","Q","R","S","T","U","V","W","X","Y","Z",
}

Y_SNAP = 3  # used only for Street Index parsing (less sensitive)
ROW_MAX_GAP = 5.0  # max vertical distance (px) to cluster words into same row
# NOTE: PDF row pitch is ~8px; PCT column is consistently +1.4px below NAME column.
# We use proximity-based clustering (group_words_into_rows) instead of fixed snap
# to robustly handle this offset without merging adjacent rows.

# ── Helpers ───────────────────────────────────────────────────────────────────

def snap_y(y, grid=Y_SNAP):
    return round(y / grid) * grid

def group_words_into_rows(words, max_gap=ROW_MAX_GAP):
    """
    Group PDF words into logical rows by clustering on y-center.
    Returns list of rows, each row is a list of (xc, word) tuples,
    sorted by x within the row.
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w[1] + w[3]) / 2)
    rows = []
    current_row = [sorted_words[0]]
    current_y = (sorted_words[0][1] + sorted_words[0][3]) / 2
    for w in sorted_words[1:]:
        yc = (w[1] + w[3]) / 2
        if abs(yc - current_y) <= max_gap:
            current_row.append(w)
            current_y = sum((ww[1]+ww[3])/2 for ww in current_row) / len(current_row)
        else:
            rows.append(current_row)
            current_row = [w]
            current_y = yc
    rows.append(current_row)
    # Convert to list of sorted (xc, word) tuples
    return [sorted([((w[0]+w[2])/2, w[4]) for w in row], key=lambda t: t[0]) for row in rows]

def in_range(x, rng):
    return rng[0] <= x <= rng[1]

def classify_x(x, col):
    """Return field name for x in given column ('L' or 'R'), or None."""
    if col == 'L':
        if in_range(x, L_V):      return 'V'
        if in_range(x, L_HOUSE):  return 'HOUSE'
        if in_range(x, L_APT):    return 'APT'
        if in_range(x, L_STREET): return 'STREET'
        if in_range(x, L_PCT):    return 'PCT'
        if in_range(x, L_NAME):   return 'NAME'
    else:
        if in_range(x, R_V):      return 'V'
        if in_range(x, R_HOUSE):  return 'HOUSE'
        if in_range(x, R_APT):    return 'APT'
        if in_range(x, R_STREET): return 'STREET'
        if in_range(x, R_PCT):    return 'PCT'
        if in_range(x, R_NAME):   return 'NAME'
    return None

def col_for_x(x):
    """Return 'L', 'R', or None based on x position."""
    if x < 310:
        return 'L'
    elif x >= 310:
        return 'R'
    return None

# ── Street Index Parser ───────────────────────────────────────────────────────

def parse_street_index(doc):
    """
    Parse pages 7–10 (indices 6–9) — Street Index.
    Returns list of {street, precinct, book_page} dicts.
    Column layout: LEFT col x<300, RIGHT col x>300
    Columns within each side: STREET | PRECINCT | PAGE
    """
    streets = []

    for page_idx in STREET_INDEX_PAGES:
        page = doc[page_idx]
        words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_idx)

        # Group by snapped y
        rows = defaultdict(list)
        for w in words:
            x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
            xc = (x0 + x1) / 2
            yc = snap_y((y0 + y1) / 2)
            rows[yc].append((xc, word))

        for y in sorted(rows.keys()):
            row_words = sorted(rows[y], key=lambda t: t[0])
            # Skip header rows
            texts = [w[1].upper() for w in row_words]
            if any(t in ("STREET", "PRECINCT", "PAGE", "WINCHESTER", "2024") for t in texts):
                continue

            # Split into left and right columns
            left  = [(x, w) for x, w in row_words if x < 300]
            right = [(x, w) for x, w in row_words if x >= 300]

            for side in [left, right]:
                if not side:
                    continue
                # In each side: leftmost words = street name, then precinct digit(s), then page number
                # Strategy: scan right-to-left; last numeric = page, second-to-last numeric = precinct
                nums = [(i, w) for i, (x, w) in enumerate(side) if w.isdigit() or (len(w) <= 2 and w.isdigit())]
                if len(nums) < 2:
                    continue
                # page_num is rightmost number, precinct is next
                page_num_idx = nums[-1][0]
                prec_idx = nums[-2][0]
                prec_val = side[prec_idx][1]
                page_val = side[page_num_idx][1]

                # Street name = everything before prec_idx
                street_parts = [w for x, w in side[:prec_idx]]
                if not street_parts:
                    continue
                street_name = " ".join(street_parts).upper()

                try:
                    precinct = int(prec_val)
                    book_page = int(page_val)
                except ValueError:
                    continue

                if 1 <= precinct <= 8:
                    streets.append({
                        "street": street_name,
                        "precinct": precinct,
                        "book_page": book_page
                    })

    # Deduplicate: if same street appears multiple times with different precincts, keep all
    # First pass: group by street
    by_street = defaultdict(list)
    for s in streets:
        by_street[s["street"]].append(s)

    result = []
    for street, entries in sorted(by_street.items()):
        if len(entries) == 1:
            result.append(entries[0])
        else:
            # Multiple entries = multi-precinct (e.g. listed once per precinct in index)
            # Keep entry with lowest precinct as primary but note all precincts
            precincts = sorted(set(e["precinct"] for e in entries))
            result.append({
                "street": street,
                "precinct": precincts[0],  # primary
                "precincts": precincts,
                "book_page": entries[0]["book_page"]
            })

    return result

# ── Alphabetical List Parser ──────────────────────────────────────────────────

def parse_alpha_list(doc):
    """
    Parse pages 106–211 (indices 105–210) — Alphabetical List.
    Returns list of {name, house, apt, street, precinct} dicts.
    Uses proximity-based row clustering to handle the ~1.4px y-offset between
    NAME and PCT columns in the PDF.
    """
    records = []

    for page_idx in ALPHA_LIST_PAGES:
        page = doc[page_idx]
        words = page.get_text("words")

        if not words:
            continue

        # Split words into left and right columns, then cluster each into rows
        left_words  = [w for w in words if (w[0]+w[2])/2 <  310]
        right_words = [w for w in words if (w[0]+w[2])/2 >= 310]

        col_word_lists = [('L', left_words), ('R', right_words)]

        # Process each column
        for col, col_words in col_word_lists:
            if not col_words:
                continue
            row_clusters = group_words_into_rows(col_words)
            for row_words in row_clusters:  # row_words is list of (xc, word) sorted by x

                # Classify each word by field
                fields = defaultdict(list)
                for xc, word in row_words:
                    field = classify_x(xc, col)
                    if field:
                        fields[field].append(word)

                # Skip if no NAME or no PCT
                if 'NAME' not in fields and 'PCT' not in fields:
                    continue

                # Skip header / section-letter rows
                name_words = fields.get('NAME', [])
                if not name_words:
                    continue
                combined = " ".join(name_words).upper()
                # Section letter headers: single alpha char
                if len(combined.strip()) == 1 and combined.strip().isalpha():
                    continue
                # Header row labels
                if combined.strip() in SKIP_WORDS or combined.strip() in (
                    "TOWN OF WINCHESTER", "ALPHABETICAL LIST", "2024 LIST"
                ):
                    continue
                # Skip "ALPHABETICAL LIST" or "TOWN OF WINCHESTER" split across words
                if all(w.upper() in SKIP_WORDS for w in name_words):
                    continue

                # Extract PCT
                pct_words = fields.get('PCT', [])
                if not pct_words:
                    continue
                pct_str = "".join(pct_words).strip()
                if not pct_str.isdigit():
                    continue
                precinct = int(pct_str)
                if not (1 <= precinct <= 8):
                    continue

                # Extract HOUSE
                house_words = fields.get('HOUSE', [])
                house_str = "".join(house_words).strip()
                # House can be numeric or alphanumeric (e.g. "12A")
                if not house_str:
                    continue
                # Normalize: strip leading zeros, keep as string
                house_num = house_str.lstrip('0') or '0'
                # Extract numeric portion for sorting
                house_num_int = int(re.sub(r'\D', '', house_num)) if re.search(r'\d', house_num) else 0

                # Extract STREET (may be multi-word)
                street_words = fields.get('STREET', [])
                street = " ".join(street_words).upper().strip()
                if not street:
                    continue

                # Extract APT (optional)
                apt_words = fields.get('APT', [])
                apt = " ".join(apt_words).strip() if apt_words else ""

                records.append({
                    "name": combined,
                    "house": house_num,
                    "house_int": house_num_int,
                    "apt": apt,
                    "street": street,
                    "precinct": precinct
                })

    return records

# ── Build House→Precinct Map ──────────────────────────────────────────────────

def build_house_precincts(records):
    """
    Build {street: {houseNum: precinct}} from all records.
    houseNum is a string (preserves "12A" etc).
    """
    hp = defaultdict(dict)
    for r in records:
        hp[r["street"]][r["house"]] = r["precinct"]
    return dict(hp)

def build_street_summary(records):
    """
    Build summary: for each street, what precincts does it appear in?
    Returns {street: [sorted unique precincts]}
    """
    by_street = defaultdict(set)
    for r in records:
        by_street[r["street"]].add(r["precinct"])
    return {s: sorted(p) for s, p in sorted(by_street.items())}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    pdf_path = os.path.abspath(pdf_path)

    if not os.path.exists(pdf_path):
        print(f"ERROR: PDF not found at {pdf_path}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Opening PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    print(f"  Total pages: {doc.page_count}")

    # 1. Parse Street Index
    print("\n[1/3] Parsing Street Index (pages 7–10)...")
    streets = parse_street_index(doc)
    print(f"  Found {len(streets)} streets in Street Index")

    # 2. Parse Alphabetical List
    print("\n[2/3] Parsing Alphabetical List (pages 106–211)...")
    records = parse_alpha_list(doc)
    print(f"  Found {len(records)} person records")

    # 3. Build house→precinct map
    print("\n[3/3] Building house→precinct maps...")
    house_precincts = build_house_precincts(records)
    street_summary  = build_street_summary(records)

    print(f"  {len(house_precincts)} streets with address data")

    # Check multi-precinct streets
    multi = {s: p for s, p in street_summary.items() if len(p) > 1}
    print(f"\n  Multi-precinct streets found ({len(multi)}):")
    for s, p in sorted(multi.items()):
        sample = sorted(house_precincts[s].items(), key=lambda x: int(re.sub(r'\D','',x[0]) or 0))[:5]
        print(f"    {s}: precincts {p}  (sample: {sample})")

    # Check Florence St specifically
    for name in ["FLORENCE ST", "FLORENCE"]:
        if name in street_summary:
            print(f"\n  FLORENCE ST: precincts {street_summary[name]}")
            break
    else:
        print("\n  WARNING: FLORENCE ST not found in Alphabetical List!")

    # Save outputs
    streets_output = {
        "source": "2024 Winchester Public Book List",
        "street_index": streets,
        "street_summary_from_alpha": street_summary,
    }
    streets_path = os.path.join(OUTPUT_DIR, "streets_data.json")
    with open(streets_path, "w") as f:
        json.dump(streets_output, f, indent=2)
    print(f"\n  Saved: {streets_path}")

    addresses_path = os.path.join(OUTPUT_DIR, "all_addresses.json")
    # Remove house_int before saving (internal sort key)
    clean_records = [{k: v for k, v in r.items() if k != 'house_int'} for r in records]
    with open(addresses_path, "w") as f:
        json.dump(clean_records, f, indent=2)
    print(f"  Saved: {addresses_path}  ({len(clean_records)} records)")

    hp_path = os.path.join(OUTPUT_DIR, "house_precincts.json")
    with open(hp_path, "w") as f:
        json.dump(house_precincts, f, indent=2)
    print(f"  Saved: {hp_path}")

    # Print quick stats
    print(f"\n── Summary ──────────────────────────────────────────")
    print(f"  Streets in Street Index:        {len(streets)}")
    print(f"  Person records (Alpha List):    {len(records)}")
    print(f"  Streets with address data:      {len(house_precincts)}")
    print(f"  Multi-precinct streets:         {len(multi)}")
    total_addr = sum(len(v) for v in house_precincts.values())
    print(f"  Total unique addresses mapped:  {total_addr}")

    doc.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
