Godfall Equipment Editor — 0.1.0
Provisional author: 高斯定理 / Gauss Theorem
Local release candidate. Not yet validated on a second PC or another real save.

WHAT IT DOES
Browse armor sets, saved loadouts, equipment and augments. Filter/sort the armory,
edit supported trait types within normal game ranges, and create modified copies
while keeping originals. Batch plans support up to eight source items. Normally
picked-up and saved copies remain after disabling the generation patch.
Experimental tools include cleansing eligible cursed items, ground-loot editing,
legacy local overrides and scoped primal reward adjustments. Disabled by default.

REQUIREMENTS
Windows x64; a legitimate local Godfall installation matching the verified build.
This build was tested against the Steam executable SHA-256:
301f90fc4f6119b64f7ef51971f6083264c4f4878500f5cd52341e4eb673b834
Different executable or UI resources are rejected. Epic/other game builds have not
been verified. Python and Node.js are included; no separate installation needed.

FIRST RUN
1. Extract the ENTIRE ZIP to a writable folder. Do not run inside the ZIP.
2. Double-click Launch.cmd. Select the Godfall folder containing Aperion.
   The included runtime is selected automatically. Choose English or 简体中文.
   Verify & Prepare reads your own original game files; it installs no patch.
3. With the game closed, open Settings and click Install Base Reader.
   The tool installs only its named additional pak, never overwrites original paks.
4. Start Godfall, open the armory, then click Refresh Loadouts in the tool.
   This reads YOUR inventory and saved armor presets. No account or save folder
   needs to be selected. Do not import someone else's equipment plans.
5. Add selected items to Batch Editor. Review before/after traits and ranges,
   save item drafts, prepare the batch, then close the game to install the batch.
6. Start a single-player mission, obtain normal loot and pick it up normally.
   Use Read Generation Status and Verify in Armory to check acquisition.
   A “generated” result alone does not mean the item was picked up and saved.

LANGUAGE & PATHS
Use the language selector in the main window; it changes presentation, not item IDs
or rules. Settings validates your game folder and build. Reopen after path changes.
Keep this tool folder in place after creating plans: plans/backups use local paths.
Use a separate clean extraction for each game installation or player profile.

SUPPORTED LIMITS
The armory picker can filter items with/without random primaries and sort random
primaries first; it remembers these choices. Classification uses actual selected
tags and native pools, separately from edit availability. Incomplete records are
not treated as fixed. The bilingual random-primary catalogue lists all 15 matching
static templates; it does not guarantee drops in every game mode.
Secondary copy editing supports ordinary/primal equipment, rank 0–5, with checks
for item family, pools, exclusions, upgrade scaling and supported parameter types.
Cleansed copy support is limited to rank-0 rings. Random primary copy editing
supports ordinary/single-Primal rank 0–5 items with matching guaranteed native
slot libraries and actual selected tags; it is no longer restricted to Blade of
Conquest. Fixed or ambiguous primary slots remain protected. One primary per source
plan; it cannot be mixed with secondary edits. Upgrade rank and mastery are kept.
Expanded support passed offline reconstruction and generation-flow checks;
verify newly generated items in game. Unsupported combinations are blocked.
This does not directly overwrite arbitrary existing items under their old IDs.
Generation is for single-player loot. Each plan independently prevents duplicates;
full reward lists defer remaining items to a later drop. Normal rewards are kept.
If the source changes after preparation, prepare again instead of forcing a write.
Only the documented normal Tower chest primal branch is in the verified loot scope;
×2 had one real chest test. ×3/×5 are not yet tested in the game.

BACKUPS & REMOVAL
Tool backups cover the managed patch and its configuration, NOT your game save.
Keep a separate game-save backup using your usual method before testing a beta.
To remove the local patch, close the game and use Disable All Patches. The tool
checks ownership and backs it up. It does not remove normally acquired copies
or reverse curse completions already saved by the game. Keep the tool's backups
until you are satisfied. Never delete or replace the game's original pak files.

DATA & TROUBLESHOOTING
This package ships a blank profile: no author's inventory, plans, game resources,
prebuilt personal patches, account information or save files. Game tables and
native translations are prepared locally from your installation. The tool stores
local inventory snapshots, plans, settings, backups and diagnostic logs afterward.
Treat a used tool folder as personal data; share only the clean distribution ZIP.
Do not move to another map before picking up generated items. Check all armory
filters when searching for a copy. A same-name random drop may not be the copy.
On a failure, retain the exact message and local log; do not repeatedly force it.
If the launcher fails, it shows a message; check local_mod/launcher_error.log.
No uploader, account login, updater or automatic publishing is included.

RELEASE STATUS
Path relocation, clean-profile runtime and offline checks are documented separately
in the local validation report. They do not prove compatibility with every PC/save.
See RELEASE-NOTICE-English.txt for the release statement, non-commercial use terms,
copyright information and the rights-dispute contact procedure.
Bundled runtimes retain their own licenses; see THIRD-PARTY-NOTICES.txt.

APPLICATION ICON
The application icon uses the image supplied by the project author and is included in this package. No game portrait is extracted.
A local shortcut named 众神陨落-装备编辑器 is generated in the package root. Rights in depicted game artwork remain with their respective holders.

UPGRADING
Disable All Patches in the old tool before installing the reader from the new folder.
Keep the old tool folder and backups. Do not distribute a used personal profile.

INVENTORY READER SETUP
First use: close the game, open Settings and install the base reader, then start the game.
After changing tool folders, an existing byte-identical base reader is verified and attached to the new local profile on refresh, without changing game files.
Other plans or different patches are never adopted automatically. Follow the message to disable them using their original tool first.

RESET APPLICATION (Settings → Reset Application)
Close the game and other editor windows first. Reset backs up and clears inventory snapshots, drafts, plans, filters/sorting, history, language and path preferences.
Existing tool patches are returned to the base reader. Game saves, acquired equipment and saved curse completions are kept. Program files, runtimes, the icon and original resource caches remain.
The tool closes on success; reopen for first-run setup. Backups are stored in 初始化备份 under the tool root and are not loaded automatically.
Reset backups contain personal data. Share the clean ZIP instead of a used tool folder.
