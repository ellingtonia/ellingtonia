#!/usr/bin/env python3

import argparse
import sqlalchemy as db
import sqlalchemy.orm as orm
import json
import os
import logging
import shutil
import sys
import time

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

Base = orm.declarative_base()


class Session(Base):
    __tablename__ = "session"

    session_id = db.Column(db.Integer, primary_key=True)
    group = db.Column(db.String, nullable=False)
    location = db.Column(db.String)
    date = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    maintainer_comment = db.Column(db.String)

    # e.g. "1924-1930.json"
    json_filename = db.Column(db.String)
    sequence_no = db.Column(db.Integer)

    # We could also set lazy=joined here to always load the associated tracks.
    # For the time being, we've used 'subqueryload' where needed.
    # The 'lazy' lets us do .filter()
    entries = orm.relationship(
        "Entry", back_populates="session", lazy="dynamic"
    )

    def __repr__(self):
        return "<Session: %d on %s>" % (self.session_id, self.date)


class EntryRelease(Base):
    __tablename__ = "take_release"

    entry_id = db.Column(db.ForeignKey("entry.entry_id"), primary_key=True)
    release_id = db.Column(
        db.ForeignKey("release.release_id"), primary_key=True
    )

    sequence_no = db.Column(db.Integer)

    entry = orm.relationship("Entry", back_populates="releases")
    release = orm.relationship("Release", back_populates="entries")
    flags = db.Column(db.String)


class Entry(Base):
    __tablename__ = "entry"

    entry_id = db.Column(db.Integer, primary_key=True)

    session_id = db.Column(db.Integer, db.ForeignKey("session.session_id"))

    sequence_no = db.Column(db.Integer)

    type = db.Column(db.String)

    value = db.Column(db.String)
    content = db.Column(db.String)

    title = db.Column(db.String)
    index = db.Column(db.String)
    matrix = db.Column(db.String)
    desor = db.Column(db.String)

    youtube = db.Column(db.String)
    spotify = db.Column(db.String)
    tidal = db.Column(db.String)

    session = orm.relationship("Session", back_populates="entries")
    releases = orm.relationship("EntryRelease", cascade="all, delete-orphan")


class Label(Base):
    __tablename__ = "label"

    label_id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String, unique=True)

    # Deliberately not unique as a few are "(Unknown)"
    name = db.Column(db.String)

    releases = orm.relationship("Release", back_populates="label")

    def __repr__(self):
        return "<label {}>".format(self.label)


class Release(Base):
    __tablename__ = "release"

    release_id = db.Column(db.Integer, primary_key=True)

    label_id = db.Column(db.Integer, db.ForeignKey("label.label_id"))
    catalog = db.Column(db.String)

    unique_label_catalog = db.UniqueConstraint("label_id", "catalog")

    discogs = db.Column(db.String)
    musicbrainz = db.Column(db.String)
    spotify = db.Column(db.String)
    tidal = db.Column(db.String)
    youtube = db.Column(db.String)

    label = orm.relationship("Label", back_populates="releases")
    entries = orm.relationship(
        "EntryRelease", back_populates="release", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return "<Release {}>".format(self.release_id)


from sqlalchemy import create_engine


def load_from_json(engine):
    with orm.Session(engine) as sq_session:
        logging.info("Importing labels")
        label_cache = {}
        with open(json_labels_path) as f:
            label_data = json.load(f)
            for label, name in label_data.items():
                label_obj = Label(label=label, name=name)
                sq_session.add(label_obj)
                label_cache[label] = label_obj

        sq_session.commit()

        release_cache = {}
        all_sessions = []
        for session_path in session_paths:
            logging.info(f"Importing {session_path}")
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
                    sequence_no=session_idx,
                )
                for entry_idx, jentry in enumerate(jsession["entries"]):
                    if jentry["type"] == "artists":
                        entry = Entry(
                            type="artists",
                            value=jentry["value"],
                            sequence_no=entry_idx,
                        )
                        sess.entries.append(entry)

                    elif jentry["type"] == "note":
                        entry = Entry(
                            type="note",
                            content=jentry["content"],
                            sequence_no=entry_idx,
                        )
                        sess.entries.append(entry)

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
                            sequence_no=entry_idx,
                        )

                        seen_releases = set()
                        idx = 0
                        for label, catalog, flags in jentry["releases"]:
                            if (label, catalog) in seen_releases:
                                logging.warning(
                                    f"Skipping duplicate release {label} {catalog}"
                                )
                                continue
                            seen_releases.add((label, catalog))

                            release = release_cache.get((label, catalog))
                            if release is None:
                                release = Release(
                                    label=label_cache[label], catalog=catalog
                                )
                                release_cache[(label, catalog)] = release

                            er = EntryRelease(
                                entry=entry,
                                release=release,
                                sequence_no=idx,
                                flags=flags,
                            )
                            idx += 1
                            entry.releases.append(er)
                        sess.entries.append(entry)
                all_sessions.append(sess)

        sq_session.add_all(all_sessions)

        with open(json_releases_path) as f:
            logging.info(f"Importing releases")
            releases_data = json.load(f)
            for label, release_data in releases_data.items():
                for catalog, release_data in release_data.items():
                    release = release_cache[(label, catalog)]
                    release.discogs = release_data.get("discogs")
                    release.musicbrainz = release_data.get("musicbrainz")
                    release.spotify = release_data.get("spotify")
                    release.tidal = release_data.get("tidal")
                    release.youtube = release_data.get("youtube")

        logging.info("Committing")
        sq_session.commit()
        logging.info("Finished import")


def save_to_json(engine):
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

    with orm.Session(engine) as sq_session:
        logging.info("Exporting labels")
        labels = list(sq_session.scalars(db.select(Label)))
        json_labels = {
            l.label: l.name
            for l in sorted(labels, key=lambda l: l.label.lower())
        }
        save_json(json_labels_path, json_labels)

        releases = list(sq_session.scalars(db.select(Release).join(Label)))
        json_releases = {}
        logging.info("Exporting releases")
        for release in releases:
            assert release.entries, f"Empty release {release}"

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
                return (
                    er.entry.session.json_filename,
                    er.entry.session.sequence_no,
                    er.entry.sequence_no,
                )

            for er in sorted(release.entries, key=sorting_key):
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
            logging.info(f"Exporting {session_path}")
            sessions = sq_session.scalars(
                db.select(Session)
                .where(Session.json_filename == os.path.basename(session_path))
                .order_by(Session.sequence_no)
            )
            json_sessions = []
            for session in sessions:
                json_entries = []
                for entry in session.entries.order_by(Entry.sequence_no):
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

                        # For some reason we can't use order_by here; it's just an instrumented list
                        releases = sorted(
                            entry.releases, key=lambda r: r.sequence_no
                        )
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


def get_engine(backup=True):
    def get():
        return db.create_engine("sqlite:///database", echo=False, future=True)

    def create():
        logging.info(f"Importing from JSON")
        engine = get()
        Base.metadata.create_all(engine)
        load_from_json(engine)
        return engine

    if os.path.exists("database"):
        if backup is True:
            shutil.copy("database", f"database.{int(time.time())}")
        return get()
    else:
        return create()


def get_label(sq_session, label):
    try:
        return sq_session.scalars(
            db.select(Label).where(Label.label == label)
        ).one()
    except db.exc.NoResultFound as e:
        logging.error(f"Could not find label {label}")
        raise e


def get_release(sq_session, label, catalog):
    label = get_label(sq_session, label)

    matching_releases = list(
        sq_session.scalars(
            db.select(Release).where(
                (Release.label == label) & (Release.catalog == catalog)
            )
        )
    )
    assert len(matching_releases) < 2
    if not matching_releases:
        return Release(label=label, catalog=catalog)
    else:
        return matching_releases[0]


def cmd_rollback(args):
    if not os.path.exists("database"):
        logging.error("No database to roll back")
        sys.exit(1)

    candidates = sorted(
        [f for f in os.listdir(".") if f.startswith("database.")],
        key=lambda s: int(s.replace("database.", "")),
    )

    if not candidates:
        logging.error("No backups to roll back")
        sys.exit(1)

    src = candidates[-1]
    logging.info(f"Moving {src} to database")
    os.rename(src, "database")


def cmd_add_label(args):
    engine = get_engine()

    with orm.Session(engine) as sq_session:

        label_obj = Label(label=args.label, name=args.name)
        sq_session.add(label_obj)

        sq_session.commit()

    return engine


def find_entries(args, sq_session):
    entries = set()

    for desor in args.desors:
        tmp = list(
            sq_session.scalars(db.select(Entry).where(Entry.desor == desor))
        )
        assert len(tmp) == 1, f"Missing or ambiguous DESOR {desor}"
        entries.update(tmp)

    for index in args.indexes:
        tmp = list(
            sq_session.scalars(db.select(Entry).where(Entry.index == index))
        )
        assert len(tmp) == 1, f"Missing or ambiguous index {index}"
        entries.update(tmp)

    return entries


def cmd_release_takes(args):
    engine = get_engine()

    with orm.Session(engine) as sq_session:
        release = get_release(sq_session, args.label, args.catalog)

        if args.release_takes_mode == "set":
            release.entries = []

        entries = find_entries(args, sq_session)

        for entry in entries:
            tmp = list(
                list(
                    sq_session.scalars(
                        db.select(EntryRelease).where(
                            (EntryRelease.entry == entry)
                            & (EntryRelease.release == release)
                        )
                    )
                )
            )
            if tmp:
                logging.warning(f"Entry {entry} already has release {release}")
                continue

            if entry.releases:
                sequence_no = entry.releases[-1].sequence_no + 1
            else:
                sequence_no = 0
            er = EntryRelease(
                entry=entry, release=release, sequence_no=sequence_no, flags=""
            )
            entry.releases.append(er)

        sq_session.commit()

    return engine


def cmd_set_take_releases(args):
    engine = get_engine()

    with orm.Session(engine) as sq_session:
        tmp = list(
            sq_session.scalars(
                db.select(Entry).where(Entry.desor == args.desor)
            )
        )
        assert len(tmp) == 1, f"Missing or ambiguous DESOR {args.desor}"
        entry = tmp[0]
        entry.releases = []

        for sequence_no, release in enumerate(args.releases):
            label, catalog = release.split(" ", 1)
            release = get_release(sq_session, label, catalog)

            er = EntryRelease(
                entry=entry, release=release, sequence_no=sequence_no, flags=""
            )
            entry.releases.append(er)

        sq_session.commit()

    return engine


def cmd_release_metadata(args):
    engine = get_engine()

    with orm.Session(engine) as sq_session:
        release = get_release(sq_session, args.label, args.catalog)

        for param in ["discogs", "musicbrainz", "spotify", "tidal"]:
            if getattr(args, param) is not None:
                setattr(release, param, getattr(args, param))

        sq_session.commit()


def cmd_duplicate_release(args):
    engine = get_engine()
    with orm.Session(engine) as sq_session:
        src = get_release(sq_session, args.label_src, args.catalog_src)
        dest = get_release(sq_session, args.label_dest, args.catalog_dest)

        # A straight copy of src.entries to dest.entries doesn't do what you
        # want
        for old_er in src.entries:
            if any(er.entry == old_er.entry for er in dest.entries):
                logging.warning(f"Entry {old_er} already has release {dest}")
                continue

            new_er = EntryRelease(
                entry=old_er.entry,
                release=dest,
                sequence_no=old_er.sequence_no,
                flags=old_er.flags,
            )
            dest.entries.append(new_er)

        sq_session.commit()


def cmd_rename_release(args):
    engine = get_engine()
    with orm.Session(engine) as sq_session:
        src = get_release(sq_session, args.label_src, args.catalog_src)
        src.label = get_label(sq_session, args.label_dest)
        src.catalog = args.catalog_dest

        sq_session.commit()


def cmd_renumber_session(args):
    engine = get_engine()
    with orm.Session(engine) as sq_session:
        sessions = list(
            sq_session.scalars(
                db.select(Session).where(Session.date == args.date_str)
            )
        )
        index = args.start_index
        for session in sessions:
            for entry in session.entries:
                if entry.index:
                    entry.index = index
                    index += 1

        sq_session.commit()


def cmd_dump_release(args):
    engine = get_engine()
    with orm.Session(engine) as sq_session:
        release = get_release(sq_session, args.label_src, args.catalog_src)
        print(f"{release.label.label} {release.catalog}")
        print(f"{len(release.entries)} takes")
        if release.discogs:
            print(release.discogs)
        print()
        entries = release.entries.copy()
        entries.sort(key=lambda er: er.entry.index)
        for entry in entries:
            title = entry.entry.title
            if entry.flags:
                title += f" ({entry.flags})"
            print(f"{entry.entry.index:<10} {title:<42} {entry.entry.desor}")
    print()


def cmd_list_label_releases(args):
    engine = get_engine()
    with orm.Session(engine) as sq_session:
        label = get_label(sq_session, args.label)
        for release in label.releases:
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

    sp_rollback = subparsers.add_parser("rollback")
    sp_rollback.set_defaults(func=cmd_rollback)

    sp_export = subparsers.add_parser(
        "export",
        help="Used to force a re-export when there are no other changes",
    )
    sp_export.set_defaults(func=lambda args: None)
    sp_export.set_defaults(export=True)

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

    sp_dump_release = subparsers.add_parser("list_label_releases")
    sp_dump_release.set_defaults(func=cmd_list_label_releases)
    sp_dump_release.add_argument("label")

    args = parser.parse_args()

    args.func(args)

    if args.export:
        save_to_json(get_engine(backup=False))


if __name__ == "__main__":
    main()
