# Agent Guidance
- data/discog contains json files for a discographic database. Most requests
will be to modify these files.
- `generated.json` is generated and should not be modified directly.
- After making source changes, always run `tools/database.py normalise`.
- If you need to, read `MAINTAINERS.md` for context on the format of the json
files etc. However for trivial edits and following the email workflow, you
probably won't need to.
- Don't update MEMORY.md. Instead offer to update AGENTS.md where appropriate.

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
- if the email includes `labels.json` / `labels_changed*.json`, apply label
changes first. This is normally a simple diff. Use `patch`, don't try anything
clever. If only one file is present, just use that file as the new
`labels.json`. Note that `labels.json` lives in data/discog.
- find the original and edited year JSON files in the extracted attachments
(there is no need to read these assuming things go smoothly).
- run `tools/import_for_agents.sh YEAR BASE_JSON MODIFIED_JSON`

`tools/import_for_agents.sh` will patch the repo file at `data/discog/YEAR.json`
and then run `./tools/database.py normalise`. Do not run this without processing
labels first.

As an LLM, it is fine to make a practical judgement about which attachment is
the base/original file and which is the changed/edited version. It should be
obvious from filenames like `1926.json` vs `1926_changed_April2026.json`, so do
not attempt clever heuristics.

Make a commit when you're done. Do not ask for confirmation. The commit message
should consist of the year (or years), then after a blank line, the email body
(from body.txt) and/or any attached text file or descriptive document. Don't
paraphrase or come up with your own commit message.

Please don't try to be clever, don't write helper python scripts, this should
all be extremely trivial. If you're stuck, say why.

You can then delete the temporary directory.
