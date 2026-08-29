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

Some sessions use a `type: "suite"` entry to group a series of takes under a shared `suite_title`. The loader keeps the suite title for subsequent takes until the `suite_title` is changed or reset to `null` (which indicates following takes are not part of a suite). Each take within the suite gets a `suite_index` giving its position within the suite (1 = first movement, 2 = second, etc.). Movements are often recorded out of order, so don't expect `suite_index` values within a session to appear as a neat ascending sequence.

## `medley` entries

A medley (a single performance stringing together several already-titled songs, e.g. a run through the band's hits) is headed by a `type: "medley"` entry:

```json
{
    "type": "medley",
    "index": "67-08-07-002",
    "matrix": null,
    "desor": "DE6773b",
    "medley_title": "Medley"
}
```

Unlike a `suite` entry, a `medley` entry is a real, addressable row: it gets its own `index` (any truthy placeholder — filled in/corrected by `normalise` exactly like a `take`'s), and it carries the medley's own `matrix`/`desor`. Only the medley itself has a matrix/DESOR; the individual songs within it don't (their own `desor` stays `null`), and `releases` only ever attach to the individual songs, never to the medley header itself.

Each song within the medley is an ordinary `take` entry with a `medley_index` field — a letter (`"a"`, `"b"`, `"c"`, ...) matching the "New DESOR" lettering convention. Both `medley_index` and the take's actual `index` are auto-generated by `normalise` from a truthy `index` placeholder, exactly like ordinary take numbering: the constituent's real `index` becomes the enclosing medley's index with the letter appended directly (no separator), e.g. medley `67-08-07-002` → constituents `67-08-07-002a`, `67-08-07-002b`, ...

A medley is ended, so that following takes are ordinary again, with a null-title reset entry:

```json
{ "type": "medley", "medley_title": null }
```

This reset is only needed when a medley's songs are followed directly by ordinary takes. Going straight from one medley into another needs no reset in between — a new `type: "medley"` entry always supersedes the previous one.

The medley header renders as a non-bold divider row, distinguishing it visually from a (bold) suite divider.

## `attacca` entries

Some runs of takes are performed with no pause between them but were never given a collective name or their own DESOR/matrix (unlike a `medley`) — for example a run through several standards during a concert, with no announced title for the run as a whole. These are marked with a pair of divider entries:

```json
{ "type": "begin_attacca" }
```
```json
{ "type": "end_attacca" }
```

Neither entry carries any other fields — there's nothing to store, since an attacca has no title, index, matrix, or DESOR of its own. Every take between a `begin_attacca` and the matching `end_attacca` keeps its `index`/`matrix`/`desor` completely unchanged from an ordinary take — nothing is derived, renumbered, or lettered for these takes. In particular, **`desor` is never touched**: two takes in the same attacca may legitimately share one DESOR letter (that's what the source New DESOR reference gives them) or may each have their own consecutive letter — either is valid, and `normalise` will never try to "fix" this (see the note on DESOR ownership in `AGENTS.md`).

`end_attacca` is only needed when an attacca's takes are followed directly by ordinary takes. Going straight from one attacca into another needs no separate reset — write `end_attacca` then `begin_attacca` back to back (or just don't bother nesting them if there's always something else in between in practice).

An attacca can appear standalone, nested inside a `suite` (sharing one `suite_index` across its takes), or spanning across a suite boundary (opening inside one suite movement and continuing past it, or running from suite material into unrelated material) — there's no restriction on how the two relate. An attacca can also appear inside a `medley` — some pieces (e.g. "Diminuendo In Blue" into "Wailing Interval") are consistently played attacca whether or not they're embedded in a broader medley that day, so a take can legitimately carry both `medley_index` and be part of an attacca run at once. The two markers render independently (the medley letter and the attacca arrow both sit inline before the title) with no visual conflict.

Rendering-wise, `begin_attacca`/`end_attacca` produce a small blank spacer row before and after the run (collapsed to one shared row when a run ends and another begins with nothing in between). The first take of the run gets a small down arrow and the last gets an up arrow against the title, pointing inward to bracket the run together; takes in between get an invisible placeholder of the same size, so every title in the run still starts at the same indent. These sit inline right before the title, the same way a medley's `suite_details` letter does, so an attacca run's titles line up with a titled medley's rather than getting their own indent (a run nested deeper, e.g. inside a suite, indents further only because the suite/medley prefix text ahead of the title is wider, not because of any attacca-specific indent). All of this is driven by an auto-generated `attacca` flag on the take (added by `normalise`, like `medley_index` — never something to type by hand) plus plain CSS sibling selectors, not any extra per-take position data.

This replaces an older ad hoc convention (still present, unconverted, in most of the JSON files) of prefixing titles with `¬` for the first song of a run and `_|`/`-&nbsp;|` for continuations, baked directly into the `title` string with no schema backing.

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
