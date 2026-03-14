# Winchester TMMA Lookup

A static web application that lets Winchester, MA residents look up their elected Town Meeting Members by street address.

## About

Winchester has a Representative Town Meeting with 192 elected members across 8 precincts (24 per precinct). This tool lets any resident quickly find the 24 members who represent their neighborhood by entering their street name.

## Features

- **Street autocomplete** — start typing any Winchester street name for instant suggestions
- **Multi-precinct disambiguation** — streets that span precinct boundaries prompt the user to select their precinct
- **Full member roster** — all 192 members, organized by precinct, with term expiration info
- **Dark/light mode** — respects system preference, with manual toggle
- **Mobile-friendly** — works on all screen sizes
- **No server required** — pure static HTML/CSS/JS, runs on any web host

## Data

- **Member roster**: as of January 7, 2026 (sourced from Google Drive: "Town Meeting Members_BY PRECINCT_as of 07 January 2026")
- **Street index**: Winchester 2024 Street Index, supplemented from precinct boundary maps
- Official source: [Winchester TMMA Directory](https://www.winchestertmma.org/directory/by-precinct-1-8)

## Deployment

This is a zero-dependency static site — upload all files to any web host:

```
index.html   — main page
data.js      — member roster + street index
app.js       — lookup logic
```

Works on InterServer's shared hosting plan. No PHP, Node.js, or database required.

## Updating Data

When the town clerk certifies new members after a March election:

1. Edit `data.js` — update the `members` object with new/changed entries
2. Update `members[precinct]` arrays for any precincts with changes
3. Update the `dataAsOf` string
4. Re-upload the file

If precinct boundaries change (redistricting), update the `streets` object accordingly.

## Sources

- [Winchester TMMA](https://www.winchestertmma.org)
- [Winchester Town Meeting](https://www.winchester.us/241/Town-Meeting)
- [Precinct Maps](https://www.winchester.us/213/Precinct-Maps)
- [MA Voter Lookup](https://www.sec.state.ma.us/WhereDoIVoteMA/WhereDoIVote)

---

*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
