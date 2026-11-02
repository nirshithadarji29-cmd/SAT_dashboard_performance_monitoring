# SAT Intelligence Platform

Streamlit dashboard over the monthly SAT accuracy reports. It reads the Excel
reports straight out of OneDrive, filters them, and shows accuracy KPIs,
category / subcategory charts, a country choropleth, and the items falling
below the 85% target.

There is **no data path stored in this repository.** The app locates the SAT
folder on your machine at startup.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Getting access to the data

The app needs the SAT folder synced to your machine by the OneDrive desktop
app. If you are not the owner of the data:

1. Ask the data owner to share the `Monthly_SAT_*` folder with you in OneDrive.
2. Open the shared folder on OneDrive on the web.
3. Choose **Add shortcut to My files**. This makes it appear in your OneDrive.
4. In Finder / Explorer, right-click that folder and choose **Always Keep on
   This Device**. Syncing the folder is not enough — by default OneDrive
   creates cloud-only placeholder files that have a size but no contents, and
   pandas cannot read them.
5. Wait for a solid green check (not a cloud icon), then start the app.

### macOS only: Full Disk Access

macOS blocks terminal access to `~/Library/CloudStorage`, where OneDrive keeps
synced files. Without it you get `Operation not permitted`.

Grant it once: **System Settings → Privacy & Security → Full Disk Access →**
enable **Terminal** (or iTerm), then restart the terminal.

Note that the shared folder is renamed by OneDrive to
`<Owner>'s files - Monthly_SAT_2026`. The app matches on `*Monthly_SAT*`, so
that prefix is handled automatically.

## How the data folder is found

Resolution order:

1. **`SAT_DATA_ROOT`** environment variable, if set. Points directly at the
   data folder. Use this for a non-standard setup, a network share, or CI.
2. **OneDrive sync folder**, discovered from the OS:
   - Windows: `%OneDriveCommercial%`, `%OneDriveConsumer%`, `%OneDrive%`
   - macOS: `~/Library/CloudStorage/OneDrive*`
   - Legacy: `~/OneDrive*`

   Within those roots, the app searches up to 3 levels deep for a folder
   matching `Monthly_SAT_*` and uses the latest match. Override the pattern
   with `SAT_FOLDER_PATTERN` if your folder is named differently.

If nothing is found, the app prints exactly what it searched — no silent
blank dashboard.

## Expected data layout

```
Monthly_SAT_2026/
  <source>/
    <month>/
      *category*.xlsx          -> category report
      *sub_category*.xlsx      -> subcategory report
```

Reports are wide format: one row per category (or subcategory), one column per
country, holding the accuracy percentage. The app melts these into long format
before charting.

## Caching

Excel files are read once and cached for one hour, so changing a filter does
not re-read from disk. Use the **Refresh data** button at the top of the page
to pick up newly added files immediately.

## Environment variables

| Variable | Purpose |
|---|---|
| `SAT_DATA_ROOT` | Absolute path to the SAT data folder. Overrides auto-discovery. |
| `SAT_FOLDER_PATTERN` | Glob for the data folder name. Default `Monthly_SAT_*`. |

## Known limitation: CI / Jenkins

Auto-discovery relies on the OneDrive **desktop client** having synced the
folder locally. A Jenkins agent has no OneDrive client, so a deployed build
must either:

- have the data mounted and `SAT_DATA_ROOT` pointed at it, or
- read from SharePoint / OneDrive over the Microsoft Graph API using an Azure
  AD app registration (not yet implemented).
