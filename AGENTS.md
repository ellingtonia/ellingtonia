# Agent Guidance
- data/discog contains json files for a discographic database. Most requests
will be to modify these files.
- `generated.json` is generated and should not be modified directly.
- After making source changes, always run `tools/database.py normalise`.
- Read `MAINTAINERS.md` for context on the format of the json files etc.
