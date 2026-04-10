# Overall structure

The bulk of the discographic data is stored in  session files, one per year e.g. `data/discog/1939.json`. Other important files are `labels.json` and `releases.json`, discussed in more detail below.

# Normalisation

Running `tools/database.py normalise` will re-format all files, run various checks and in some cases download external data from Discogs. You should do this after every operation to check your changes are valid.

The normalise command also supports `--no-scrape-discogs` if you want to skip Discogs lookups during validation.

Other normalisation steps are performed:

* "index" numbers: these will get re-generated. So if you add a new take, you don't need to add 1 to everything that follows. However, it's important to note that not every take has an index number - it can also be null.
* Alphabetical sorting of releases within sessions.


# Session files (e.g. `data/discog/1939.json`)

Each file consists of a series of sessions, and within each session a series of entries. Each entry has a `type` e.g. `take` (i.e. a recording), `artists` (info about musicians etc.) or `note` for a general note.

Here is what the `1939.json` file would look like if it contained only a single interview.
```json
[
    {
        "group": "DUKE ELLINGTON",
        "location": "Stockholm, Sweden",
        "date": "29 April 1939",
        "description": "Swedish Radio Broadcast",
        "entries": [
            {
                "type": "artists",
                "value": "Duke Ellington, Manne Berggren(tk)"
            },
            {
                "type": "take",
                "index": "39-04-29-001",
                "matrix": null,
                "title": "Interview by Berggren",
                "releases": [
                    {
                        "label": "CaR",
                        "catalog": "CAP-21452"
                    },
                    {
                        "label": "Mx",
                        "catalog": "MLP-1001"
                    }
                ],
                "desor": "DE3908a",
                "youtube": "https://www.youtube.com/watch?v=ABCDEFG",
                "tidal": "https://tidal.com/browse/track/12345678"
            },
            {
                "type": "note",
                "content": "An example note. Ellingtonia \"Loves You Madly\"."
            }
        ]
    }
]
```

Sessions have the following mandatory properties:

* `group`
* `location`
* `date` - this should be in the format `"01 January 1930"` wherever possible
* `description`

Sessions have the following optional properties:

* `same_session`: if this is `true` then it marks a continuation of the same session with a different `group`. The `date` should be repeated and should be the same.
* `index_date`: if you see `"index_date": 241101`, it means that while the date is approximate, for numbering purposes we assume a date of `24-11-01` (i.e. 1st of November 1924).
* `maintainer_comment`: this is rarely used, but can hold info for the maintainer not for public display.

## "artists" entries

This is a simple section. They always have the form:
```json
{
    "type": "artists",
    "value": "Duke Ellington, Manne Berggren(tk)"
}
```

## "note" entries

Again very simple:
```json
{
    "type": "note",
    "content": "An example note. Ellingtonia \"Loves You Madly\"."
}
```

The loader also accepts `"value"` in place of `"content"` for note entries, so older JSON may use either key.

## `suite` entries

Some sessions use a `type: "suite"` entry to group a series of takes under a shared `suite_title`. The loader keeps the suite title for subsequent takes until the `suite_title` is changed or reset to `null` (which indicates following takes are not part of a suite).

## `take` entries

Takes have the following properties, all of which must be present:

* `index`: may be null. Otherwise should be e.g. `"24-11-01-0001"`. But as discussed above, it will be filled-in for you during normalisation.
* `matrix`: may be null.
* `title`: this is mainly obvious. The convention for singing is `"I Can't Give You Anything But Love - vIM,BC"`.
* `desor`: may be null

They may also have the following links. These are to be used for a single entry only (i.e. not for a whole album):

* `youtube`
* `spotify`
* `tidal`
* `file`
* `other`

Within each `take` there is a `releases` section, which looks like this:
```json
"releases": [
    {
        "label": "(F)RCA",
        "catalog": "FPM-1-7047"
    },
    {
        "label": "Cl(F)",
        "catalog": "805"
    },
    {
        "label": "RCA",
        "catalog": "09026-63386-2",
        "disc": "8",
        "track": 12,
        "length": 199,
        "title": "Never No Lament",
        "flags": "*‡"
    }
]
```

Every release must have `label` and `catalog` fields. The following fields are also supported:

* `disc`: disc number (e.g. of a box set)
* `track`: track number
* `length`: in seconds
* `title`: title used on the record, if different
* `flags`: can be any of `*`, `‡`, or a combination
  * `*` after a release denotes that only part of the take has been used for the issued title.
  * `‡` indicates a release is not confirmed.
* `first_issue`: boolean; set to `true` if this release is the first issue for this `take`

# Release metadata (`data/discog/releases.json`)

Release metadata is stored separately in `data/discog/releases.json`. This file is organised first by label code, then by catalog number, for example:
```json
{
    "AJ": {
        "R2 74315": {
            "discogs": "https://www.discogs.com/release/12552483-Duke-Ellington-Historically-Speaking-The-Duke",
            "spotify": "https://open.spotify.com/album/4iYz6htNriFtdpgqZNDWSW?si=rS9PkQLAQZ2h_i7E_xrEWw",
            "tidal": "https://tidal.com/browse/album/31803968",
            "title": "Historically Speaking - The Duke",
            "format": "CD"
        }
    }
}
```

These entries are not attached to a specific `take`; they describe release-level metadata for the pair of `label` + `catalog` used by `releases` entries.

If `discogs` is provided, `title` and `format` are updated automatically.

Supported fields include:

* `discogs`, `musicbrainz`, `amazon`, `allmusic`, `archive`, `spotify`, `tidal`, `youtube`, `file`, `other`
* `title`
* `format`
* `note`
* `release_date`

## Other `data/discog` files

There are a few additional data files under `data/discog/` that are used by tooling and should not normally be edited directly:

* `labels.json` — maps label codes to display names.
* `titles.json` — this is displayed more-or-less directly in the discography and is self-explanatory.
* `instruments.json` — as above.

## Editing instruments

These live in `data/discog/instruments.json`. The nature of the file should be self-explanatory and it's short.
