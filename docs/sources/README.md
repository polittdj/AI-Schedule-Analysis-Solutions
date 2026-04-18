# docs/sources/ — Source File Manifest

This directory holds the approved source documents referenced by the
`.claude/skills/` SKILL.md files. It is the authoritative citation
store for all `[TAG] §... p.N` pointers across this repository.

## Present in this repository (18 files)

NASA-governance sources:

- `N_PR_8000_004C_.pdf` — NPR 8000.4C, 19 Apr 2022
- `NID_7120_148_.pdf` — NID 7120.148 transmitting NPR 7120.5 Rev F
- `GPR_7120_7B_Admin_Ext_08_09_2023.pdf` — GPR 7120.7B
- `schedule-management-handbook-20240315-update.pdf` — NASA Schedule
  Management Handbook (SMH) Rev 2, 15 Mar 2024
- `nasaevmimplementationhandbook.pdf` — NASA EVM Implementation Handbook
- `NASA_Acronyms.pdf` — NASA acronym list (scanned; limited text
  extraction)

DCMA/industry schedule-assessment sources (partial — see "Missing"
below):

- `SSINASAunderstandingdrivingslack.pdf` — SSI presentation on NASA
  driving slack

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

## Missing from this repository (6 files — user action required)

These files are referenced as **approved sources** by one or more skills
but are not yet committed to the repository. They must be copied in by
the repository owner from the local project directory (typically
`/mnt/project/` in the user's working environment) and committed
separately. The Session 18b cleanup branch does **not** fabricate
placeholders for them.

1. `Universal_Claude_Code_Master_Prompt_Template.txt` — tag [UPT]
2. `Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt`
   — tag [UPT2]
3. `Schedule-Forensics-Claude-Code-Prompt-v3.md` — tag [V3P]
4. `Papisito_Paste_Ready_Next_Steps.docx` — tag [PRNS]
5. `Edwards_DCMA_14Point_Assessment_2016.pdf` — tag [ED]
6. `RonWinter_DCMA_14Point_Assessment_2011.pdf` — tag [RW]

### Suggested commands for the user

From the repository root:

```
cp /mnt/project/Universal_Claude_Code_Master_Prompt_Template.txt docs/sources/
cp /mnt/project/Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt docs/sources/
cp /mnt/project/Schedule-Forensics-Claude-Code-Prompt-v3.md docs/sources/
cp /mnt/project/Papisito_Paste_Ready_Next_Steps.docx docs/sources/
cp /mnt/project/Edwards_DCMA_14Point_Assessment_2016.pdf docs/sources/
cp /mnt/project/RonWinter_DCMA_14Point_Assessment_2011.pdf docs/sources/
git add docs/sources/
git commit -m "docs/sources: restore 6 missing approved-source files"
```

Adjust paths to match the actual location of the files on the user's
workstation. Source-file locations are the responsibility of the
repository owner.

## Approved-source tag dictionary (quick reference)

| Tag   | Document                                                               |
| ----- | ---------------------------------------------------------------------- |
| UPT   | Universal_Claude_Code_Master_Prompt_Template.txt (missing)             |
| UPT2  | Universal_Claude_Code_Master_TooL_Development_Prompt_Template.txt (missing) |
| V3P   | Schedule-Forensics-Claude-Code-Prompt-v3.md (missing)                  |
| LL    | Schedule_Forensics_Lessons_Learned.md                                  |
| PRNS  | Papisito_Paste_Ready_Next_Steps.docx (missing)                         |
| PERG  | Schedule_Forensics_Prompt_Engineering_Reference_Guide_Ed1_4.docx       |
| SMH   | schedule-management-handbook-20240315-update.pdf                       |
| NPR8K | N_PR_8000_004C_.pdf                                                    |
| NID   | NID_7120_148_.pdf                                                      |
| GPR   | GPR_7120_7B_Admin_Ext_08_09_2023.pdf                                   |
| SSI   | SSINASAunderstandingdrivingslack.pdf                                   |
| ED    | Edwards_DCMA_14Point_Assessment_2016.pdf (missing)                     |
| RW    | RonWinter_DCMA_14Point_Assessment_2011.pdf (missing)                   |
| DECM  | DeltekDECMMetricsJan2022.xlsx                                          |
| DMG   | DeltekAcumen88MetricDevelopersGuide.pdf                                |
| ATO   | DeltekAcumen88TechnicalOverviewandSystemRequirements.pdf               |
| AQS   | DeltekAcumen88QuickStartGuide.pdf                                      |
| AIG   | DeltekAcumen88InstallationGuide.pdf                                    |
| ASI   | DeltekAcumen88InstallingAcumenUsingASilentInstall.pdf                  |
| API   | DeltekAcumen88APIGuide.pdf                                             |
| ACD   | DeltekAcumen88CostDataCsvStructure.pdf                                 |
| ARN   | DeltekAcumen88ReleaseNotes.pdf                                         |

## Authoritative scope rule

Each SKILL.md enforces a per-skill source-approval matrix. A tag that
is "approved" for one skill is not automatically approved for another.
See the Session 18a audit record for the authoritative per-skill
matrix.
