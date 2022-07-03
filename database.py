#!/usr/bin/env python3

import argparse
import collections
import json
import os
import logging

from dataclasses import dataclass

json_prefix = "data/discog"
json_labels_path = json_prefix + "/labels.json"
json_releases_path = json_prefix + "/releases.json"

session_paths = [
    json_prefix + "/1924-1930.json",
    json_prefix + "/1931-1940.json",
    json_prefix + "/1941-1950.json",
    json_prefix + "/1951-1960.json",
    json_prefix + "/1961-1970.json",
    json_prefix + "/1971-1974.json",
]


# Need eq=False as we have duplicates
@dataclass(frozen=True, eq=False)
class Session:
    group: str
    location: str
    date: str
    description: str
    maintainer_comment: str

    # e.g. "1924-1930.json"
    json_filename: str


@dataclass(frozen=False, eq=False)
class Entry:
    type: str

    value: str = None
    content: str = None

    title: str = None
    index: str = None
    matrix: str = None
    desor: str = None

    youtube: str = None
    spotify: str = None
    tidal: str = None

    session: Session = None


@dataclass(frozen=True)
class Label:
    label: str
    name: str


@dataclass(frozen=False, eq=False)
class Release:
    label: Label
    catalog: str

    discogs: str = None
    musicbrainz: str = None
    spotify: str = None
    tidal: str = None
    youtube: str = None


@dataclass(frozen=True)
class EntryRelease:
    entry: Entry
    release: Release
    flags: str


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
        self._labels[label.label] = label

    def get_label(self, label_code):
        return self._labels[label_code]

    def all_labels(self):
        return sorted(
            self._labels.values(), key=lambda label: label.label.lower()
        )

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
        self._entry_releases_by_release[entry_release.release].append(
            entry_release
        )

    def remove_entry_release(self, entry_release):
        self._entry_releases_by_entry[entry_release.entry].remove(entry_release)
        self._entry_releases_by_release[entry_release.release].remove(
            entry_release
        )

    def entry_releases_from_release(self, release):
        return self._entry_releases_by_release[release]

    def entry_releases_from_entry(self, release):
        return self._entry_releases_by_entry[release]

    def entry_from_desor(self, desor):
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


def load_from_json():
    database = Database()

    with open(json_labels_path) as f:
        label_data = json.load(f)
        for label, name in label_data.items():
            database.add_label(Label(label=label, name=name))

    for session_path in session_paths:
        with open(session_path) as f:
            json_sessions = json.load(f)

        for session_idx, jsession in enumerate(json_sessions):
            sess = Session(
                group=jsession["group"],
                location=jsession["location"],
                date=jsession["date"],
                description=jsession["description"],
                maintainer_comment=jsession.get("maintainer_comment", ""),
                json_filename=os.path.basename(session_path),
            )
            entries = []
            for entry_idx, jentry in enumerate(jsession["entries"]):
                if jentry["type"] == "artists":
                    entry = Entry(
                        type="artists",
                        value=jentry["value"],
                    )
                    entries.append(entry)

                elif jentry["type"] == "note":
                    entry = Entry(
                        type="note",
                        content=jentry["content"],
                    )
                    entries.append(entry)

                elif jentry["type"] == "take":
                    entry = Entry(
                        type="take",
                        index=jentry["index"],
                        matrix=jentry["matrix"],
                        title=jentry["title"],
                        desor=jentry["desor"],
                        youtube=jentry.get("youtube"),
                        spotify=jentry.get("spotify"),
                        tidal=jentry.get("tidal"),
                    )

                    seen_releases = set()
                    for label, catalog, flags in jentry["releases"]:
                        if (label, catalog) in seen_releases:
                            logging.warning(
                                f"Skipping duplicate release {label} {catalog}"
                            )
                            continue
                        seen_releases.add((label, catalog))

                        release = database.get_release(
                            database.get_label(label), catalog
                        )

                        er = EntryRelease(
                            entry=entry,
                            release=release,
                            flags=flags,
                        )
                        database.add_entry_release(er)
                    entries.append(entry)

            database.add_session(sess, entries)

    with open(json_releases_path) as f:
        releases_data = json.load(f)
        for label, label_releases in releases_data.items():
            for catalog, release_data in label_releases.items():
                release = database.get_release(
                    database.get_label(label), catalog
                )
                release.discogs = release_data.get("discogs")
                release.musicbrainz = release_data.get("musicbrainz")
                release.spotify = release_data.get("spotify")
                release.tidal = release_data.get("tidal")
                release.youtube = release_data.get("youtube")

                if release.discogs:
                    assert "discogs" in release.discogs
                if release.musicbrainz:
                    assert "musicbrainz" in release.musicbrainz
                if release.spotify:
                    assert "spotify" in release.spotify
                if release.tidal:
                    assert "tidal" in release.tidal
                if release.youtube:
                    assert "youtube" in release.youtube

    return database


def save_to_json(database):
    def save_json(path, obj, ensure_ascii=False):
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(obj, f, indent=4, ensure_ascii=ensure_ascii)
                f.write("\n")
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise e
        os.rename(tmp_path, path)

    labels = database.all_labels()
    json_labels = {
        l.label: l.name for l in sorted(labels, key=lambda l: l.label.lower())
    }
    save_json(json_labels_path, json_labels)

    releases = database.all_releases()
    json_releases = {}
    for release in releases:
        entries = database.entry_releases_from_release(release)
        assert entries, f"Empty release {release}"

        json_releases.setdefault(release.label.label, {})

        json_release = {"takes": []}
        if release.discogs:
            json_release["discogs"] = release.discogs
        if release.musicbrainz:
            json_release["musicbrainz"] = release.musicbrainz
        if release.spotify:
            json_release["spotify"] = release.spotify
        if release.tidal:
            json_release["tidal"] = release.tidal
        if release.youtube:
            json_release["youtube"] = release.youtube
        json_releases[release.label.label][release.catalog] = json_release

        def sorting_key(er):
            return er.entry.session.json_filename

        for er in sorted(entries, key=sorting_key):
            json_entry = {
                "title": er.entry.title,
                "flags": er.flags,
                "index": er.entry.index,
                "matrix": er.entry.matrix,
                "desor": er.entry.desor,
                "page": er.entry.session.json_filename.replace(".json", ""),
                "youtube": er.entry.youtube,
                "spotify": er.entry.spotify,
                "tidal": er.entry.tidal,
            }
            if er.entry.youtube:
                json_entry["youtube"] = er.entry.youtube
            if er.entry.spotify:
                json_entry["spotify"] = er.entry.spotify
            if er.entry.tidal:
                json_entry["tidal"] = er.entry.tidal
            json_release["takes"].append(json_entry)

    # Consistent sorting
    json_releases = {
        k: dict(sorted(v.items())) for k, v in sorted(json_releases.items())
    }
    save_json(json_releases_path, json_releases)

    for session_path in session_paths:
        sessions = [
            session
            for session in database.all_sessions()
            if session.json_filename == os.path.basename(session_path)
        ]
        json_sessions = []
        for session in sessions:
            json_entries = []
            for entry in database.get_entries(session):
                json_entry = {"type": entry.type}
                if entry.type == "artists":
                    json_entry["value"] = entry.value
                elif entry.type == "note":
                    json_entry["content"] = entry.content
                elif entry.type == "take":
                    json_entry["index"] = entry.index
                    json_entry["matrix"] = entry.matrix
                    json_entry["title"] = entry.title
                    json_entry["releases"] = []
                    json_entry["desor"] = entry.desor

                    if entry.youtube:
                        json_entry["youtube"] = entry.youtube
                    if entry.spotify:
                        json_entry["spotify"] = entry.spotify
                    if entry.tidal:
                        json_entry["tidal"] = entry.tidal

                    releases = database.entry_releases_from_entry(entry)
                    for entry_release in releases:
                        json_entry["releases"].append(
                            (
                                entry_release.release.label.label,
                                entry_release.release.catalog,
                                entry_release.flags,
                            )
                        )

                json_entries.append(json_entry)

            jsession = {
                "group": session.group,
                "location": session.location,
                "date": session.date,
                "description": session.description,
                "entries": json_entries,
            }
            if session.maintainer_comment:
                jsession["maintainer_comment"] = session.maintainer_comment
            json_sessions.append(jsession)
        save_json(session_path, json_sessions, ensure_ascii=True)


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
    existing_entries = frozenset(
        er.entry for er in database.entry_releases_from_release(release)
    )

    if args.release_takes_mode == "set":
        release.entries = []

    entries = find_entries(args, database)

    for entry in entries:
        if entry in existing_entries:
            logging.warning(f"Entry {entry} already has release {release}")
            continue

        er = EntryRelease(entry=entry, release=release, flags="")
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


def cmd_release_metadata(args):
    database = load_from_json()

    release = database.get_release(database.get_label(args.label), args.catalog)

    for param in ["discogs", "musicbrainz", "spotify", "tidal"]:
        if getattr(args, param) is not None:
            setattr(release, param, getattr(args, param))

    save_to_json(database)


def cmd_duplicate_release(args):
    database = load_from_json()

    src = database.get_release(
        database.get_label(args.label_src), args.catalog_src
    )
    dest = database.get_release(
        database.get_label(args.label_dest), args.catalog_dest
    )

    src_entries = database.entry_releases_from_release(src)
    dest_releases = [
        er.release for er in database.entry_releases_from_release(dest)
    ]

    for src_er in src_entries:
        if src_er.release in dest_releases:
            logging.warning(f"Entry {src_er} already has release {dest}")
            continue

        dest_er = EntryRelease(
            entry=src_er.entry,
            release=dest,
            flags=src_er.flags,
        )
        database.add_entry_release(dest_er)

    save_to_json(database)


def cmd_rename_release(args):
    database = load_from_json()

    release = database.get_release(
        database.get_label(args.label_src), args.catalog_src
    )

    database.rename_release(
        release, database.get_label(args.label_dest), args.catalog_dest
    )

    save_to_json(database)


def cmd_renumber_session(args):
    database = load_from_json()
    sessions = [
        session
        for session in database.all_sessions()
        if session.date == args.date_str
    ]
    index = args.start_index
    for session in sessions:
        for entry in database.get_entries(session):
            if entry.index:
                entry.index = str(index)
                index += 1

    save_to_json(database)


def cmd_dump_release(args):
    def na(val):
        return "N/A" if val is None else str(val)

    database = load_from_json()

    release = database.get_release(
        database.get_label(args.label_src), args.catalog_src
    )
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


def cmd_list_label_releases(args):
    database = load_from_json()
    label = database.get_label(args.label)
    releases = [
        release for release in database.all_releases() if release.label is label
    ]
    releases.sort(key=lambda release: release.catalog)
    for release in releases:
        print(release.catalog)


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

    sp_add_label = subparsers.add_parser("add_label")
    sp_add_label.set_defaults(func=cmd_add_label)
    sp_add_label.add_argument("label")
    sp_add_label.add_argument("name")

    sp_add_release = subparsers.add_parser("add_release_takes")
    sp_add_release.set_defaults(func=cmd_release_takes)
    sp_add_release.set_defaults(release_takes_mode="add")
    sp_add_release.add_argument("label")
    sp_add_release.add_argument("catalog")
    sp_add_release.add_argument("--desors", nargs="+", default=[])
    sp_add_release.add_argument("--indexes", nargs="+", default=[])

    sp_set_release = subparsers.add_parser("set_release_takes")
    sp_set_release.set_defaults(func=cmd_release_takes)
    sp_set_release.set_defaults(release_takes_mode="set")
    sp_set_release.add_argument("label")
    sp_set_release.add_argument("catalog")
    sp_set_release.add_argument("--desors", nargs="+", default=[])
    sp_set_release.add_argument("--indexes", nargs="+", default=[])

    sp_set_take_releases = subparsers.add_parser("set_take_releases")
    sp_set_take_releases.set_defaults(func=cmd_set_take_releases)
    sp_set_take_releases.add_argument("--desor", required=True)
    sp_set_take_releases.add_argument("--releases", nargs="+")

    sp_add_release = subparsers.add_parser("release_metadata")
    sp_add_release.set_defaults(func=cmd_release_metadata)
    sp_add_release.add_argument("label")
    sp_add_release.add_argument("catalog")
    sp_add_release.add_argument("--discogs")
    sp_add_release.add_argument("--musicbrainz")
    sp_add_release.add_argument("--spotify")
    sp_add_release.add_argument("--tidal")

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

    sp_renumber_session = subparsers.add_parser("renumber_session")
    sp_renumber_session.set_defaults(func=cmd_renumber_session)
    sp_renumber_session.add_argument("date_str")
    sp_renumber_session.add_argument("start_index", type=int)

    sp_dump_release = subparsers.add_parser("dump_release")
    sp_dump_release.set_defaults(func=cmd_dump_release)
    sp_dump_release.add_argument("label_src")
    sp_dump_release.add_argument("catalog_src")

    sp_list_label_releases_release = subparsers.add_parser(
        "list_label_releases"
    )
    sp_list_label_releases_release.set_defaults(func=cmd_list_label_releases)
    sp_list_label_releases_release.add_argument("label")

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
