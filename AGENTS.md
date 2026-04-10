# Agent Guidance
- data/discog contains json files for a discographic database. Most requests
will be to modify these files.
- `generated.json` is generated and should not be modified directly.
- After making source changes, always run `tools/database.py normalise`.
- Read `MAINTAINERS.md` for context on the format of the json files etc.

# Processing emails
You may be asked to process an email file. This will typically have several
attachments. Usually they take the form of a json file for a particular year,
and the un-modified version of the same. In which case, apply the diff between
the two files. The commit message should be approximately verbatim from what's
in the email (with any formalities removed) and/or any attached text file or
descriptive document. The first line of the commit message should simply be the
year or years processed (e.g. "1940" or "1940, 1941").

Sometimes you will also have to update labels.json or another file similarly.
