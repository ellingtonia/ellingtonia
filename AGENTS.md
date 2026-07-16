# Agent Guidance
- data/discog contains json files for a discographic database. Most requests
will be to modify these files.
- The ordering of `take` entries within a session is chronological (recording
order) and should not be changed without explicit instruction.
- `generated.json` is generated and should not be modified directly.
- After making source changes, always run `tools/database.py normalise` (without a leading `./`).
- If you need to, read `MAINTAINERS.md` for context on the format of the json
files etc. However for trivial edits and following the email workflow, you
probably won't need to.
- Don't update MEMORY.md. Instead offer to update AGENTS.md where appropriate.
- In general, look at your permissions and try to use commands that will avoid
requiring confirmation from the user.
- Carefully read through your permissions to try to avoid the user needing
to approve commands. Consider whether using `&&` might cause an un-needed approval.

# Processing emails
You may be asked to process an email file. This will typically have several
attachments. Usually they take the form of a json file for a particular year,
and the unmodified version of the same, plus possibly some new labels.

The preferred workflow is:
- make a new, empty temporary directory under `.agents-tmp/` (let's assume it's
called `TMP`). Create the parent directory if needed.
- extract the `.eml` contents using `tools/unpack_eml.py --output-dir TMP file.eml`
  - the script prints the full paths of the directory and files it creates
  - note the paths are nested by email file name (to handle multiple emails)
  - there is always a body.txt which you should read and consider for the commit message.
- if the email includes `labels.json` / `labels_changed*.json`, apply label
changes first. This is normally a simple diff. Use `patch`, don't try anything
clever. If only one file is present, just use that file as the new
`labels.json`. Note that `labels.json` lives in data/discog.
- find the original and edited year JSON files in the extracted attachments
(there is no need to read these assuming things go smoothly).
- run `tools/import_for_agents.sh YEAR BASE_JSON MODIFIED_JSON`

`tools/import_for_agents.sh` will patch the repo file at `data/discog/YEAR.json`
and then run `tools/database.py normalise`. Do not run this without processing
labels first.

As an LLM, it is fine to make a practical judgement about which attachment is
the base/original file and which is the changed/edited version. It should be
obvious from filenames like `1926.json` vs `1926_changed_April2026.json`, so do
not attempt clever heuristics.

After importing, update `content/discography/changes.md`. Add or extend the
entry for the current month (e.g. `## June 2026`) with a brief bullet per year
summarising what changed, based on the email body. Keep it succinct.

`changes.md` is read by people interested in the discography itself, not the
repo's implementation. Only mention substantive content changes (corrections
to instrumentation, catalog numbers, track listings, dates, etc). Don't
mention incidental JSON/data-formatting fixes (e.g. a string "17" corrected to
the number 17, or other things only a developer would care about).

Make a commit when you're done. Do not ask for confirmation. The commit message
should consist of the year (or years), then after a blank line, the email body
(from body.txt) and/or any attached text file or descriptive document. Don't
paraphrase or come up with your own commit message.

Please don't try to be clever, don't write helper python scripts, this should
all be extremely trivial. If you're stuck, say why.

You can then delete the temporary directory.

# Ambiguous/uncertain dates
If a session has a date string that cannot be parsed (e.g. "Possibly 08 November
1952", "circa Spring 1943"), `tools/database.py normalise` will fail with
"Could not parse ...". The fix is to add an `index_date` field to that session
in the JSON, giving a numeric date for sorting purposes:

    "index_date": YYMMDD

where the formula is `(year - 1900) * 10000 + month * 100 + day`. You can
confirm the right date by checking the `index` values of the takes within that
session (e.g. `"index": "52-11-08-001"` → 521108). Add the field directly to
the session object alongside `"date"`.
