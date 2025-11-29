#!/usr/bin/env python3

import argparse
import datetime
import collections
import csv
import json
import os
import logging
import re
import requests
import time
import glob

from dataclasses import dataclass

# Last bit: prevent accidentally including query string
DISCOGS_REGEX = "https://www.discogs.com/release/([0-9]+)-[^?]*"

json_prefix = "data/discog"
json_labels_path = json_prefix + "/labels.json"
json_releases_path = json_prefix + "/releases.json"
json_generated_path = json_prefix + "/generated.json"


# Need eq=False as we have duplicates
@dataclass(frozen=False, eq=False)
class Session:
    group: str
    location: str
    # May or may not be a valid date (e.g. "Circa Jan 1932")
    date_str: str
    same_session: bool
    description: str
    maintainer_comment: str

    # e.g. "1924-1930.json"
    json_filename: str

    # date used for indexing purposes if the actual date is uncertain
    date: int

    def year(self):
        # TODO This is horrible, switch to a proper date time when we get rid of
        # nonsense dates.
        return 1900 + self.date // 10000


ENTRY_LINKS = ["youtube", "spotify", "tidal", "file", "other"]


class Entry:
    type: str

    value: str = None
    content: str = None

    title: str = None
    suite: str = None
    suite_title: str = None
    suite_index: int = None
    index: str = None
    matrix: str = None
    desor: str = None

    session: Session = None

    # TODO: Add the concept of a rejected entry here
    # TODO: Add "Recorded as" for the original recording title, e.g. "DE2802c"
    # was first released as "Harlem Twist".


Entry.__annotations__.update({key: str for key in ENTRY_LINKS})
for key in ENTRY_LINKS:
    setattr(Entry, key, None)
Entry = dataclass(frozen=False, eq=False)(Entry)


@dataclass(frozen=True, eq=True, order=True)
class Label:
    label: str
    name: str


RELEASE_LINKS = [
    "discogs",
    "musicbrainz",
    "amazon",
    "allmusic",
    "archive",
    "spotify",
    "tidal",
    "youtube",
    "file",
    "other",
    # TODO: These should be considered separately
    "title",
    "format",
]


class Release:
    label: Label
    catalog: str

    title: str = None
    format: str = None
    note: str = None
    release_date: str = None


Release.__annotations__.update({key: str for key in RELEASE_LINKS})
for key in RELEASE_LINKS:
    setattr(Release, key, None)
Release = dataclass(frozen=False, eq=False)(Release)


@dataclass(frozen=True)
class EntryRelease:
    entry: Entry
    release: Release
    flags: str
    disc: str
    track: int
    length: int  # in seconds
    title: str
    first_issue: bool = False


class Database:
    def __init__(self):
        self._sessions = []
        self._releases = {}
        self._entries = {}
        self._labels = {}
        self._entry_releases_by_entry = collections.defaultdict(list)
        self._entry_releases_by_release = collections.defaultdict(list)
        self._entries_by_desor = {}
        self._entries_by_index = {}

    def add_session(self, session, entries):
        for entry in entries:
            entry.session = session

            if entry.desor in self._entries_by_desor:
                self._entries_by_desor[entry.desor] = None  # Ambiguous
            else:
                self._entries_by_desor[entry.desor] = entry

            if entry.index in self._entries_by_index:
                self._entries_by_index[entry.index] = None  # Ambiguous
            else:
                self._entries_by_index[entry.index] = entry

        self._sessions.append(session)
        self._entries[session] = entries

    def all_sessions(self):
        return self._sessions[:]

    def add_label(self, label):
        assert label.label not in self._labels, "Duplicate label"

        self._labels[label.label] = label

    def get_label(self, label_code):
        return self._labels[label_code]

    def rename_label(self, label, label_code, name):
        del self._labels[label.label]
        self._labels[label_code] = label
        label.label = label_code
        label.name = name

    def all_labels(self):
        return sorted(self._labels.values(), key=lambda label: label.label.lower())

    def get_release(self, label, catalog):
        assert isinstance(label, Label)

        return self._releases.setdefault(
            (label, catalog), Release(label=label, catalog=catalog)
        )

    def rename_release(self, release, label, catalog):
        assert isinstance(release.label, Label)
        assert isinstance(label, Label)
        assert self._releases[(release.label, release.catalog)] is release

        del self._releases[(release.label, release.catalog)]
        release.label = label
        release.catalog = catalog
        self._releases[(label, catalog)] = release

    def all_releases(self):
        return list(self._releases.values())

    def get_entries(self, session):
        return self._entries[session]

    def add_entry_release(self, entry_release):
        assert isinstance(entry_release, EntryRelease)
        assert isinstance(entry_release.entry, Entry)
        assert isinstance(entry_release.release, Release)
        self._entry_releases_by_entry[entry_release.entry].append(entry_release)
        self._entry_releases_by_release[entry_release.release].append(entry_release)

    def remove_entry_release(self, entry_release):
        self._entry_releases_by_entry[entry_release.entry].remove(entry_release)
        self._entry_releases_by_release[entry_release.release].remove(entry_release)

    def entry_releases_from_release(self, release):
        return self._entry_releases_by_release[release][:]

    def entry_releases_from_entry(self, release):
        return self._entry_releases_by_entry[release][:]

    def entry_from_desor(self, desor):
        assert desor, "Empty desor"
        if desor not in self._entries_by_desor:
            raise KeyError(f"Missing DESOR {desor}")

        entry = self._entries_by_desor[desor]
        if entry is None:
            raise KeyError(f"Ambiguous DESOR {desor}")

        return entry

    def entry_from_index(self, index):
        if index not in self._entries_by_index:
            raise KeyError(f"Missing index {index}")

        entry = self._entries_by_index[index]
        if entry is None:
            raise KeyError(f"Ambiguous index {index}")

        return entry

    def validate_releases(self):
        seen = set()
        for label, catalog in self._releases.keys():
            key = (label, catalog.replace(" ", "-"))
            if key in seen:
                raise RuntimeError("Ambiguous releases detected", label.label, catalog)
            seen.add(key)


def fix_date(date_str):
    date_str = date_str.strip()

    parts = date_str.split()
    if len(parts) != 3:
        return date_str, None

    d, m, y = parts
    try:
        d = int(d)
        y = int(y)
    except ValueError:
        return date_str, None
    m = m.lower()
    m = m[0].upper() + m[1:]

    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    try:
        m_numeric = months.index(m) + 1
    except ValueError:
        return date_str, None

    return f"{d:02d} {m} {y}", (y - 1900) * 10000 + m_numeric * 100 + d


def load_from_json():
    database = Database()

    with open(json_labels_path) as f:
        label_data = json.load(f)
        for label, name in label_data.items():
            database.add_label(Label(label=label, name=name))

    all_indices = set()

    session_paths = glob.glob("data/discog/19*.json")
    for session_path in session_paths:
        with open(session_path) as f:
            try:
                json_sessions = json.load(f)
            except json.decoder.JSONDecodeError as e:
                e.args += (session_path,)
                raise

        old_date = None

        for jsession in json_sessions:
            suite_title = None
            if not "date" in jsession:
                raise RuntimeError(f"Missing date, previous session was {old_date}")

            date_str, date = fix_date(jsession["date"])

            # "index_date" is used to indicate indexing if the date is ambiguous
            if date is None:
                if not "index_date" in jsession:
                    raise RuntimeError(f"Could not parse {date_str}")

                date = jsession["index_date"]
            else:
                assert "index_date" not in jsession, date_str

            if date != old_date:
                idx = 1

            same_session = jsession.get("same_session", False)
            if same_session:
                assert date == old_date, (old_date, date)

            old_date = date

            sess = Session(
                group=jsession["group"],
                location=jsession["location"],
                date_str=date_str,
                same_session=same_session,
                description=jsession["description"],
                maintainer_comment=jsession.get("maintainer_comment", ""),
                json_filename=os.path.basename(session_path),
                date=date,
            )

            entries = []
            for jentry in jsession["entries"]:
                assert "type" in jentry, date_str
                if jentry["type"] == "artists":
                    entry = Entry(
                        type="artists",
                        value=jentry["value"],
                    )
                    entries.append(entry)

                elif jentry["type"] == "note":
                    # Ezio sometimes types "value", maybe we should switch to
                    # that anyway.
                    if "value" in jentry:
                        content = jentry["value"]
                    else:
                        content = jentry["content"]
                    entry = Entry(type="note", content=content)
                    entries.append(entry)

                elif jentry["type"] == "suite":
                    suite_title = jentry["suite_title"]
                    # We deliberately don't append this to the list of entries.
                    # Instead we re-insert "suite" entries when generating
                    # yearly json files and release data.
                    # It's overall simpler to keep the python database clean and
                    # not have entries for "begin suite" (which don't mean
                    # anything on their own). But for actual formatting (and to
                    # avoid repetition) it's useful to have them in the json.
                    # Note that go templates are very limited and it's hard to
                    # do "is this entry in the same suite".

                elif jentry["type"] == "take":
                    index = jentry["index"]

                    title = jentry["title"]

                    # Tidy up whitespace issues. Annoyingly hugo doesn't cope
                    # well with leading nbsps, so we add a minus.
                    title.replace("\u00a0", "&nbsp;")
                    n_leading_whitespace = len(title) - len(title.lstrip())
                    if n_leading_whitespace > 0:
                        title = "-" + "&nbsp;" * n_leading_whitespace + title.lstrip()

                    # If an index is present, we always replace it with an
                    # auto-number, so errors get corrected.
                    if index:
                        str_date = str(date)
                        index = (
                            f"{str_date[0:2]}-{str_date[2:4]}-{str_date[4:6]}-{idx:03}"
                        )
                        idx += 1

                        # Check for duplicates
                        assert index not in all_indices, (index, title)
                        all_indices.add(index)

                    suite_index = (
                        int(jentry["suite_index"]) if "suite_index" in jentry else None
                    )

                    entry = Entry(
                        type="take",
                        index=index,
                        matrix=jentry["matrix"],
                        title=title,
                        suite_title=suite_title,
                        suite_index=suite_index,
                        desor=jentry["desor"],
                    )

                    for key in ENTRY_LINKS:
                        setattr(entry, key, jentry.get(key))

                    seen_releases = set()

                    # Sort the releases in the obvious way while we're here
                    # (case-insensitive).
                    def sort_key(release_dict):
                        return (
                            release_dict["label"].lower(),
                            release_dict["catalog"].lower(),
                        )

                    for release_dict in sorted(jentry["releases"], key=sort_key):
                        label = release_dict["label"]
                        catalog = release_dict["catalog"]
                        if (label, catalog) in seen_releases:
                            logging.warning(
                                f"Skipping duplicate release {label} {catalog}"
                            )
                            continue
                        seen_releases.add((label, catalog))

                        release = database.get_release(
                            database.get_label(label), catalog
                        )

                        flags = release_dict.get("flags")

                        if flags is not None:
                            if flags == "":
                                flags = None
                            else:
                                for flag in flags:
                                    assert flag in "*‡", flag

                        er_title = release_dict.get("title")
                        if er_title == "":
                            er_title = None

                        er = EntryRelease(
                            entry=entry,
                            release=release,
                            flags=flags,
                            disc=release_dict.get("disc"),
                            track=release_dict.get("track"),
                            length=release_dict.get("length"),
                            first_issue=release_dict.get("first_issue"),
                            title=er_title,
                        )
                        database.add_entry_release(er)
                    entries.append(entry)
                else:
                    raise RuntimeError(f"Unrecognised entry type: {jentry['type']}")

            database.add_session(sess, entries)

    with open(json_releases_path) as f:
        releases_data = json.load(f)
        for label, label_releases in releases_data.items():
            for catalog, release_data in label_releases.items():
                release = database.get_release(database.get_label(label), catalog)

                release.release_date = release_data.get("release_date")
                release.note = release_data.get("note")

                for key in RELEASE_LINKS:
                    val = release_data.get(key)
                    setattr(release, key, val)

    database.validate_releases()
    return database


def save_json(path, obj):
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(obj, f, indent=4, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise e
    os.rename(tmp_path, path)


def save_releases_to_json(database, generated):
    def entry_release_sort_key(er):
        disc = er.disc

        # Disc could be e.g. [Side] "A" rather than a number
        if disc is None:
            disc = ""
        else:
            try:
                disc = format(int(disc), "-03")
            except (ValueError, TypeError) as e:
                pass

        track = er.track
        if track is None:
            track = 0

        # Can be None for e.g. "Medley" (which shouldn't itself appear in the release)
        index = "" if er.entry.index is None else er.entry.index
        return (disc, track, index)

    releases = database.all_releases()
    json_releases = {}
    for release in releases:
        entries = database.entry_releases_from_release(release)
        if not entries:
            if generated:
                continue
            if not generated:
                # Only warn once (in the non-generated stage)
                logging.warning(f"Empty release {release}; discarding")
                # TODO: Resume purging empty manual releases with "continue"

        entries.sort(key=entry_release_sort_key)

        json_release = {}

        for key in RELEASE_LINKS:
            if value := getattr(release, key):
                json_release[key] = value

        if release.note:
            json_release["note"] = release.note

        if release.release_date:
            json_release["release_date"] = release.release_date

        if generated:
            json_release["entries"] = []
            json_release["n_takes"] = len(entries)
            suite_title = None

            for er in entries:
                if er.entry.suite_title != suite_title:
                    suite_title = er.entry.suite_title
                    json_release["entries"].append(
                        {"type": "suite", "suite_title": suite_title}
                    )
                disc_track = None
                if er.disc and er.track:
                    disc_track = f"{er.disc}-{er.track}"
                elif er.disc:
                    disc_track = f"{er.disc}"
                elif er.track:
                    disc_track = f"{er.track}"

                length = None
                if er.length:
                    length = f"{er.length//60}:{er.length%60:-02}"

                year = er.entry.session.year()
                if year < 1930:
                    page = "1924-1929"
                elif year < 1940:
                    page = "1930-1939"
                elif year < 1950:
                    page = "1940-1949"
                elif year < 1960:
                    page = "1950-1959"
                elif year < 1970:
                    page = "1960-1969"
                else:
                    page = "1970-1974"

                json_entry = {
                    "type": "take",
                    "title": er.entry.title,
                    "flags": er.flags,
                    "index": er.entry.index,
                    "matrix": er.entry.matrix,
                    "desor": er.entry.desor,
                    "page": page,
                    "as_title": er.title,
                    "disc_track": disc_track,
                    "length": length,
                    "suite_title": er.entry.suite_title,
                    "suite_index": er.entry.suite_index,
                }
                for key in ENTRY_LINKS:
                    json_entry[key] = getattr(er.entry, key)

                json_release["entries"].append(json_entry)

        # Skip empty entries
        if json_release:
            json_releases.setdefault(release.label.label, {})
            json_releases[release.label.label][release.catalog] = json_release

    # Consistent sorting
    json_releases = {
        k: dict(sorted(v.items())) for k, v in sorted(json_releases.items())
    }

    if generated:
        save_json(json_generated_path, {"releases": json_releases})
    else:
        save_json(json_releases_path, json_releases)


def save_to_json(database):

    labels = database.all_labels()
    json_labels = {
        l.label: l.name for l in sorted(labels, key=lambda l: l.label.lower())
    }
    save_json(json_labels_path, json_labels)

    save_releases_to_json(database, generated=False)
    save_releases_to_json(database, generated=True)

    sessions_by_year = {}
    for session in database.all_sessions():
        sessions_by_year.setdefault(session.year(), []).append(session)

    for session_year, sessions in sessions_by_year.items():
        session_path = f"data/discog/{session_year}.json"
        json_sessions = []
        for session in sessions:
            json_entries = []
            suite_title = None
            for entry in database.get_entries(session):
                if entry.type == "take" and entry.suite_title != suite_title:
                    suite_title = entry.suite_title
                    json_entries.append({"type": "suite", "suite_title": suite_title})
                json_entry = {"type": entry.type}
                if entry.type == "artists":
                    json_entry["value"] = entry.value
                elif entry.type == "note":
                    json_entry["content"] = entry.content
                elif entry.type == "suite":
                    json_entry["suite_title"] = entry.suite_title
                elif entry.type == "take":
                    json_entry["index"] = entry.index
                    json_entry["matrix"] = entry.matrix
                    json_entry["title"] = entry.title
                    json_entry["releases"] = []
                    json_entry["desor"] = entry.desor

                    if entry.suite_index:
                        json_entry["suite_index"] = entry.suite_index

                    for key in ENTRY_LINKS:
                        if value := getattr(entry, key):
                            json_entry[key] = value

                    releases = database.entry_releases_from_entry(entry)
                    for entry_release in releases:
                        release_details = {
                            "label": entry_release.release.label.label,
                            "catalog": entry_release.release.catalog,
                        }
                        if entry_release.flags is not None:
                            release_details["flags"] = entry_release.flags
                        if entry_release.disc is not None:
                            release_details["disc"] = entry_release.disc
                        if entry_release.first_issue:
                            release_details["first_issue"] = True
                        if entry_release.track is not None:
                            release_details["track"] = entry_release.track
                        if entry_release.length is not None:
                            release_details["length"] = entry_release.length
                        if entry_release.title is not None:
                            release_details["title"] = entry_release.title
                        json_entry["releases"].append(release_details)

                json_entries.append(json_entry)

            jsession = {
                "group": session.group,
                "location": session.location,
                "date": session.date_str,
            }

            # Careful ordering
            if session.date != fix_date(session.date_str)[1]:
                jsession["index_date"] = session.date

            if session.same_session:
                jsession["same_session"] = True
            jsession["description"] = session.description
            jsession["entries"] = json_entries

            if session.maintainer_comment:
                jsession["maintainer_comment"] = session.maintainer_comment

            json_sessions.append(jsession)
        save_json(session_path, json_sessions)


class Discogs:
    def __init__(self):
        self._cache_dir = ".discogs_cache"
        os.makedirs(self._cache_dir, exist_ok=True)

    def get(self, release_number):
        path = f"{self._cache_dir}/{release_number}.json"
        if os.path.exists(path):
            return json.load(open(path))
        else:
            data = self._get_impl(release_number)
            json.dump(data, open(path, "w"), indent=4)
            return data

    def _get_impl(self, release_number):
        headers = {"User-Agent": "EllingtoniaTool/1.0 +http://ellingtonia.com"}
        url = f"https://api.discogs.com/releases/{release_number}"

        logging.info(f"Querying {url}")

        while True:
            result = requests.get(url, headers=headers)
            if result.status_code == 429:
                logging.info(f"Sleeping")
                time.sleep(60)
            else:
                break

        time.sleep(60 / 24)  # Rate limit is 1/25
        return result.json()


def scrape_discogs(database):
    def format_to_str(json_format):
        if "qty" in json_format and int(json_format["qty"]) > 1:
            return f"{json_format['qty']}x{json_format['name']}"
        else:
            return json_format["name"]

    discogs = Discogs()

    for release in database.all_releases():
        if release.discogs:
            release_number = re.match(DISCOGS_REGEX, release.discogs).groups()[0]

            jdata = discogs.get(release_number)

            release.title = jdata["title"]

            release.format = ", ".join(
                sorted(format_to_str(f) for f in jdata["formats"])
            )


def cmd_normalise(args):
    database = load_from_json()

    # Some checks
    for release in database.all_releases():
        if release.discogs:
            assert re.match(DISCOGS_REGEX, release.discogs)

        # Checks very roughly that URLs etc look reasonable
        for key in [
            "discogs",
            "musicbrainz",
            "amazon",
            "allmusic",
            "spotify",
            "tidal",
            "youtube",
        ]:
            if v := getattr(release, key):
                assert key in v, (release, key, v)

    if args.scrape_discogs:
        scrape_discogs(database)
    save_to_json(database)


def cmd_add_label(args):
    database = load_from_json()

    database.add_label(Label(label=args.label, name=args.name))

    save_to_json(database)


def find_entries(args, database):
    entries = set()

    for desor in args.desors:
        entries.add(database.entry_from_desor(desor))

    for index in args.indexes:
        entries.add(database.entry_from_index(index))

    return entries


def cmd_release_takes(args):
    database = load_from_json()

    release = database.get_release(database.get_label(args.label), args.catalog)
    entries = find_entries(args, database)

    if args.release_takes_mode == "remove":
        entry_releases = database.entry_releases_from_release(release)

        for entry in entries:
            tmp = [er for er in entry_releases if er.entry == entry]
            if len(tmp) != 1:
                raise KeyError(f"Entry not present to remove: {entry}")
            database.remove_entry_release(tmp[0])

    else:
        existing_entries = frozenset(
            er.entry for er in database.entry_releases_from_release(release)
        )

        for entry in entries:
            if entry in existing_entries:
                logging.warning(f"Entry {entry} already has release {release}")
                continue

            er = EntryRelease(
                entry=entry,
                release=release,
                disc=None,
                flags=None,
                track=None,
                length=None,
                title=None,
            )
            database.add_entry_release(er)

    save_to_json(database)


def cmd_set_take_releases(args):
    database = load_from_json()

    entry = database.entry_from_desor(args.desor)
    for er in database.entry_releases_from_entry(entry):
        database.remove_entry_release(er)

    for release in args.releases:
        label, catalog = release.split(" ", 1)
        release = database.get_release(database.get_label(label), catalog)

        er = EntryRelease(entry=entry, release=release, flags="")
        database.add_entry_release(er)

    save_to_json(database)


def cmd_delete_release(args):
    database = load_from_json()

    release = database.get_release(database.get_label(args.label), args.catalog)
    entries = database.entry_releases_from_release(release)
    for entry in entries:
        database.remove_entry_release(entry)

    save_to_json(database)


def cmd_release_metadata(args):
    database = load_from_json()

    release = database.get_release(database.get_label(args.label), args.catalog)

    for param in RELEASE_LINKS:
        if getattr(args, param) is not None:
            setattr(release, param, getattr(args, param))

    save_to_json(database)


def cmd_duplicate_release(args):
    database = load_from_json()

    src = database.get_release(database.get_label(args.label_src), args.catalog_src)
    dest = database.get_release(database.get_label(args.label_dest), args.catalog_dest)

    src_entries = database.entry_releases_from_release(src)
    dest_releases = [er.release for er in database.entry_releases_from_release(dest)]

    for src_er in src_entries:
        if src_er.release in dest_releases:
            logging.warning(f"Entry {src_er} already has release {dest}")
            continue

        dest_er = EntryRelease(
            entry=src_er.entry,
            release=dest,
            flags=src_er.flags,
            # Note we don't copy these fields
            disc=None,
            track=None,
            length=None,
            title=None,
        )
        database.add_entry_release(dest_er)

    save_to_json(database)


def cmd_rename_release(args):
    database = load_from_json()

    release = database.get_release(database.get_label(args.label_src), args.catalog_src)

    database.rename_release(
        release, database.get_label(args.label_dest), args.catalog_dest
    )

    save_to_json(database)


def cmd_rename_label(args):
    database = load_from_json()

    label = database.get_label(args.label_src)
    database.rename_label(label, args.label_dest, args.name_dest)

    save_to_json(database)


def cmd_dump_release(args):
    def na(val):
        return "N/A" if val is None else str(val)

    database = load_from_json()

    release = database.get_release(database.get_label(args.label_src), args.catalog_src)
    entries = database.entry_releases_from_release(release)
    entries.sort(key=lambda er: na(er.entry.index))

    print(f"{release.label.label} {release.catalog}")
    print(f"{len(entries)} takes")

    if release.discogs:
        print(release.discogs)
    print()

    for entry in entries:
        title = entry.entry.title
        if entry.flags:
            title += f" ({entry.flags})"
        print(f"{na(entry.entry.index):<10} {title:<42} {entry.entry.desor}")

    print()


def cmd_list_releases(args):
    database = load_from_json()
    releases = sorted(
        database.all_releases(), key=lambda release: (release.label, release.catalog)
    )
    for release in releases:
        print(f"{release.label.label}\t{release.catalog}")


def cmd_add_streaming(args):
    database = load_from_json()

    label = database.get_label(args.label)
    max_release = max(
        [int(r.catalog) for r in database.all_releases() if r.label == label]
    )

    release = database.get_release(label, str(max_release + 1))
    release.youtube = args.link
    entries = find_entries(args, database)

    for entry in entries:
        er = EntryRelease(
            entry=entry,
            release=release,
            disc=None,
            track=None,
            title=None,
            length=None,
            flags="",
        )
        database.add_entry_release(er)

    save_to_json(database)


def cmd_import_csv(args):
    database = load_from_json()

    with open(args.path) as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        dict_reader = csv.DictReader(f, dialect=dialect)

        for row in dict_reader:
            if not row["ndesor"].strip():
                continue

            release = database.get_release(
                database.get_label(row["label"]), row["catalog"]
            )
            try:
                entry = database.entry_from_desor(row["ndesor"].strip())
            except KeyError as e:
                print(row, e)
                raise

            length = None
            if row.get("length"):
                minutes, seconds = row["length"].split(":")
                length = int(minutes) * 60 + int(seconds)

            # Remove any existing EntryRelease
            for old_er in database.entry_releases_from_entry(entry):
                if old_er.release == release:
                    database.remove_entry_release(old_er)

            track = None
            if row.get("track"):
                track = int(row["track"])

            disc = None
            if row.get("disc"):
                disc = int(row["disc"])

            er = EntryRelease(
                entry=entry,
                release=release,
                flags=row.get("flags", ""),
                disc=disc,
                track=track,
                title=row.get("title"),
                first_issue=row.get("first_issue"),
                length=length,
            )
            database.add_entry_release(er)

    save_to_json(database)


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export",
        action="store_true",
        help="Do not update the JSON (to speed things up when running multiple commands",
    )

    subparsers = parser.add_subparsers(required=True)

    sp_normalise = subparsers.add_parser("normalise")
    sp_normalise.add_argument(
        "--no-scrape-discogs", dest="scrape_discogs", action="store_false"
    )
    sp_normalise.set_defaults(func=cmd_normalise)

    sp_add_label = subparsers.add_parser("add_label")
    sp_add_label.set_defaults(func=cmd_add_label)
    sp_add_label.add_argument("label")
    sp_add_label.add_argument("name")

    def release_takes(name, mode):
        sp = subparsers.add_parser(name)
        sp.set_defaults(func=cmd_release_takes)
        sp.set_defaults(release_takes_mode=mode)
        sp.add_argument("label")
        sp.add_argument("catalog")
        sp.add_argument("--desors", nargs="+", default=[])
        sp.add_argument("--indexes", nargs="+", default=[])

    release_takes("add_release_takes", "add")
    release_takes("remove_release_takes", "remove")

    sp_set_take_releases = subparsers.add_parser("set_take_releases")
    sp_set_take_releases.set_defaults(func=cmd_set_take_releases)
    sp_set_take_releases.add_argument("--desor", required=True)
    sp_set_take_releases.add_argument("--releases", nargs="+")

    sp_delete_release = subparsers.add_parser("delete_release")
    sp_delete_release.set_defaults(func=cmd_delete_release)
    sp_delete_release.add_argument("label")
    sp_delete_release.add_argument("catalog")

    sp_add_release = subparsers.add_parser("release_metadata")
    sp_add_release.set_defaults(func=cmd_release_metadata)
    sp_add_release.add_argument("label")
    sp_add_release.add_argument("catalog")

    for key in RELEASE_LINKS:
        sp_add_release.add_argument(f"--{key}")

    sp_duplicate_release = subparsers.add_parser("duplicate_release")
    sp_duplicate_release.set_defaults(func=cmd_duplicate_release)
    sp_duplicate_release.add_argument("label_src")
    sp_duplicate_release.add_argument("catalog_src")
    sp_duplicate_release.add_argument("label_dest")
    sp_duplicate_release.add_argument("catalog_dest")

    sp_rename_release = subparsers.add_parser("rename_release")
    sp_rename_release.set_defaults(func=cmd_rename_release)
    sp_rename_release.add_argument("label_src")
    sp_rename_release.add_argument("catalog_src")
    sp_rename_release.add_argument("label_dest")
    sp_rename_release.add_argument("catalog_dest")

    sp_rename_label = subparsers.add_parser("rename_label")
    sp_rename_label.set_defaults(func=cmd_rename_label)
    sp_rename_label.add_argument("label_src")
    sp_rename_label.add_argument("label_dest")
    sp_rename_label.add_argument("name_dest")

    sp_dump_release = subparsers.add_parser("dump_release")
    sp_dump_release.set_defaults(func=cmd_dump_release)
    sp_dump_release.add_argument("label_src")
    sp_dump_release.add_argument("catalog_src")

    sp_dump_release = subparsers.add_parser("add_streaming")
    sp_dump_release.set_defaults(func=cmd_add_streaming)
    sp_dump_release.add_argument("label")
    sp_dump_release.add_argument("link")
    sp_dump_release.add_argument("--desors", nargs="+", default=[])
    sp_dump_release.add_argument("--indexes", nargs="+", default=[])

    sp_import_csv = subparsers.add_parser("import_csv")
    sp_import_csv.set_defaults(func=cmd_import_csv)
    sp_import_csv.add_argument("path")

    sp_list_releases_release = subparsers.add_parser("list_releases")
    sp_list_releases_release.set_defaults(func=cmd_list_releases)

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
