# docs/sources/ — Source File Manifest

This directory holds the approved source documents referenced by the
`.claude/skills/` SKILL.md files. It is the authoritative citation
store for all `[TAG] §... p.N` pointers across this repository.

## File counts

This manifest counts source files two ways:

- **22 tagged sources.** Each entry in the tag dictionary below maps to
  exactly one file in this directory; all 22 are now present.
- **24 total source files in `docs/sources/`.** The 22 tagged sources
  plus 2 untagged supplementary files retained for analyst convenience
  (`nasaevmimplementationhandbook.pdf`,  `NASA_Acronyms.pdf`). The
  Session 18c audit's "expected 23" figure was an off-by-one from
  loose accounting; the authoritative numbers are 22 tagged / 24 total.

`README.md` itself is not counted as a source file.

## Present in this repository (24 files)

NASA-governance sources:

- `N_PR_8000_004C_.pdf` — NPR 8000.4C, 19 Apr 2022
- `NID_7120_148_.pdf` — NID 7120.148 transmitting NPR 7120.5 Rev F
- `GPR_7120_7B_Admin_Ext_08_09_2023.pdf` — GPR 7120.7B
- `schedule-management-handbook-20240315-update.pdf` — NASA Schedule
  Management Handbook (SMH) Rev 2, 15 Mar 2024

Untagged supplementary NASA references (not cited by any skill, retained
for analyst convenience):

- `nasaevmimplementationhandbook.pdf` — NASA EVM Implementation Handbook
- `NASA_Acronyms.pdf` — NASA acronym list (scanned; limited text
  extraction)

DCMA / industry schedule-assessment sources:

- `SSINASAunderstandingdrivingslack.pdf` — SSI presentation on NASA
  driving slack
- `Edwards_DCMA_14-Point_Assessment_2016.pdf` — Edwards DCMA 14-Point
  Assessment, 2016
- `RonWinter_DCMA_14-Point_Assessment_2011.pdf` — Ron Winter DCMA
  14-Point Assessment, 2011

Deltek Acumen 8.8 documentation set:

- `DeltekAcumen88APIGuide.pdf`
- `DeltekAcumen88CostDataCsvStructure.pdf`
- `DeltekAcumen88InstallationGuide.pdf`
- `DeltekAcumen88InstallingAcumenUsingASilentInstall.pdf`
- `DeltekAcumen88MetricDevelopersGuide.pdf`
- `DeltekAcumen88QuickStartGuide.pdf`
- `DeltekAcumen88ReleaseNotes.pdf`
- `DeltekAcumen88TechnicalOverviewandSystemRequirements.pdf`
- `DeltekDECMMetricsJan2022.xlsx`

Internal project sources:

- `Schedule_Forensics_Lessons_Learned.md` — [LL]
- `Schedule_Forensics_Prompt_Engineering_Reference_Guide_Ed1_4.docx`
  — [PERG]
- `Papisito_Paste_Ready_Next_Steps.docx` — [PRNS]
- `Universal_Claude_Code_Master_Prompt_Template.txt` — [UPT]
- `Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt`
  — [UPT2]
- `Schedule-Forensics-Claude-Code-Prompt-v3.md` — [V3P]

## Missing from this repository

None. The six files previously listed as missing (UPT, UPT2, V3P, PRNS,
ED, RW) were uploaded to `main` via direct-to-main commit `29bd250`
("Add files via upload") and are now present in the file list above.

## Approved-source tag dictionary (quick reference)

| Tag   | Document                                                               |
| ----- | ---------------------------------------------------------------------- |
| UPT   | Universal_Claude_Code_Master_Prompt_Template.txt                       |
| UPT2  | Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt      |
| V3P   | Schedule-Forensics-Claude-Code-Prompt-v3.md                            |
| LL    | Schedule_Forensics_Lessons_Learned.md                                  |
| PRNS  | Papisito_Paste_Ready_Next_Steps.docx                                   |
| PERG  | Schedule_Forensics_Prompt_Engineering_Reference_Guide_Ed1_4.docx       |
| SMH   | schedule-management-handbook-20240315-update.pdf                       |
| NPR8K | N_PR_8000_004C_.pdf                                                    |
| NID   | NID_7120_148_.pdf                                                      |
| GPR   | GPR_7120_7B_Admin_Ext_08_09_2023.pdf                                   |
| SSI   | SSINASAunderstandingdrivingslack.pdf                                   |
| ED    | Edwards_DCMA_14-Point_Assessment_2016.pdf                              |
| RW    | RonWinter_DCMA_14-Point_Assessment_2011.pdf                            |
| DECM  | DeltekDECMMetricsJan2022.xlsx                                          |
| DMG   | DeltekAcumen88MetricDevelopersGuide.pdf                                |
| ATO   | DeltekAcumen88TechnicalOverviewandSystemRequirements.pdf               |
| AQS   | DeltekAcumen88QuickStartGuide.pdf                                      |
| AIG   | DeltekAcumen88InstallationGuide.pdf                                    |
| ASI   | DeltekAcumen88InstallingAcumenUsingASilentInstall.pdf                  |
| API   | DeltekAcumen88APIGuide.pdf                                             |
| ACD   | DeltekAcumen88CostDataCsvStructure.pdf                                 |
| ARN   | DeltekAcumen88ReleaseNotes.pdf                                         |

### Filename canonicalization note

Where an on-disk filename and an earlier prose reference disagree, the
**on-disk filename is canonical**. The Edwards 2016 and Ron Winter 2011
DCMA papers were uploaded with `14-Point` (hyphenated); the Rev 4
handoff ledger and earlier audit notes used `14Point` (concatenated).
This manifest's `[ED]` and `[RW]` rows above use the hyphenated form to
match the on-disk filenames; the eight skill SKILL.md files reference
these papers exclusively via the `[ED]` / `[RW]` bracket tags (never by
filename) and required no edit during this reconciliation.

## Authoritative scope rule

Each SKILL.md enforces a per-skill source-approval matrix. A tag that
is "approved" for one skill is not automatically approved for another.
See the Session 18a audit record for the authoritative per-skill
matrix.
