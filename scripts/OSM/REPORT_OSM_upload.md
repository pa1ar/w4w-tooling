# OSM Smoothness Tag Upload – Proof of Execution

This document summarizes how we programmatically added the `smoothness` tag to an OpenStreetMap way using our Wheels4Wheels CLI tools. It walks through: selecting a location by coordinates, identifying the OSM way, confirming the way, checking and creating/updating the tag, and submitting a changeset with a clear comment.

## Scope
The goal is to showcase principal possibility of programmatic enrichment of OSM with data from our scooter telemetry. Please note that despite terminal-based showcase, this flow can be converted to a web application later to allow even non-technical users to enrich the map with the tool. The creation of a web application is outside of the scope of this proof of execution.

- Location tested: lat 50.328132, lon 8.738048
- Target way: `Hardbäumchesweg` – Way ID `313853519`
- Tag applied: `smoothness=intermediate`
- Changeset link: https://www.openstreetmap.org/changeset/172968694
- Way link (current state): https://www.openstreetmap.org/way/313853519

## Tools
- CLI: `scripts/OSM/osm_edit.py` and helpers in `scripts/OSM/osm_utils.py` (will be shared via repository later)
- Auth: OpenStreetMap OAuth 2.0, out-of-band (OOB) redirect (`urn:ietf:wg:oauth:2.0:oob`)
- Python 3.12, uv with installed dependencies (os, sys, json, argparse, pathlib, typing, urllib.parse, requests, requests_oauthlib, dotenv, lxml, time)
- Credentials retrieved from OSM, via environment variables in `.env` (client ID/secret not included in this report)

## Methods
We took a known road, which doesn't have a smoothness tag yet, and attempted to apply the tag to it.
Here is how the road looked on OpenStreetMap before we applied the tag:

![Before – Map](images/osm-before-pushing-map.png)
Here is how the changesets looked before we applied the tag:
![Before – Changesets](images/osm-before-pushing-changesets.png)

## 1) Login
First, we need to login to retrieve the access token:

```bash
uv run python scripts/OSM/osm_edit.py login
```

This will authenticate the command line tool to access the OSM API and connect the user, the app created by the user, to the changeset that we will upload.

## 2) From Coordinates to Way ID
As we will get the coordinates from the scooter telemetry later, we need to find the way ID first, by having the coordinates on our hands. We can't just select the way, so we need to select it during the enrichment process. We query [Overpass API](https://dev.overpass-api.de/overpass-doc/en/criteria/union.html) to find candidate ways around the given coordinates and present them for selection. Example usage of the CLI command we have:

```bash
uv run python scripts/OSM/osm_edit.py find-way --lat 50.328132 --lon 8.738048
```

## 3) Selecting the Way
The CLI lists nearby highway ways with useful metadata (name, surface, tracktype, existing smoothness) in a somewhat user-friendly way. We confirm the intended way interactively, or auto-confirm with `-y`.

Example (interactive):
```bash
uv run python scripts/OSM/osm_edit.py find-way \
  --lat 50.328132 --lon 8.738048
# ... select: Way 313853519
```

Non-interactive selection:
```bash
uv run python scripts/OSM/osm_edit.py find-way \
  --lat 50.328132 --lon 8.738048 -y
```

## 4) Checking Existing Tags
Before creating a changeset, we fetch the latest way XML from the OSM API and inspect tags:

```python
way_xml = get_way(way_id, access_token, config)
way = way_xml.find('way')
current = None
for tag in way.findall('tag'):
    if tag.get('k') == 'smoothness':
        current = tag.get('v')
        break
```

Created behavior:
- If `smoothness` exists with a different value → prompt to override.
- If `smoothness` does not exist → prompt to create.
- `-y` auto-confirms both decisions.

## 5) Applying the Tag and Uploading
If confirmed, the CLI opens a changeset, modifies tags, uploads, and closes the changeset:

```bash
uv run python scripts/OSM/osm_edit.py set-tag \
  --lat 50.328132 --lon 8.738048 \
  --key smoothness \
  --value intermediate \
  --comment "[w4w] accessibility map enrichment script testing"
```

Core upload flow (excerpt):
```python
changeset_id = create_changeset(access_token, config, comment)
modified_xml = modify_way_tags(way_xml, 'smoothness', 'intermediate', changeset_id)
new_version = upload_way(way_id, modified_xml, access_token, config)
close_changeset(changeset_id, access_token, config)
```

![CLI output](images/cli-output.png)

## Result of the changeset application

Public audit links:
- Changeset: https://www.openstreetmap.org/changeset/172968694
- Way (post-change): https://www.openstreetmap.org/way/313853519

![After – Map](images/osm-after-pushing-map.png)

![After – Changesets](images/osm-after-pushing-changesets.png)

## Commenting and Auditability
Every change is wrapped in an OSM changeset with a clear comment. For this test we used an easily identifiable comment, which clearly marks the changes as a test made by the Wheels4Wheels project:
```
[w4w] accessibility map enrichment script testing
```


## Summary
- We demonstrated a complete end-to-end flow for enriching OSM with `smoothness`.
- The process works: find way from coordinates, confirm, detect/create/override tag, upload via changeset with a clear audit trail.
- The tooling supports both interactive and batched, non-interactive (`-y`) workflows.

## Next Steps
- Process the scooter telemetry data to get the coordinates portionized
- Find the way and apply the tag to the ways that the scooter rider has passed through
- Document the process
- Create a repository with scripts for future contributors to use and improve