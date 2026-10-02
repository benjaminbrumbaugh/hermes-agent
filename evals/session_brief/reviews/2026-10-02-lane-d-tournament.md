# Lane D tournament review

Status: **no_candidate_beats_current**

This report separates machine grader claims from the human pixel review. The screenshots are the evidence layer; Elo and model agreement are decision aids, not proof of glanceability by themselves.

## Run receipt

- Seed: `20261002`; candidates: beacon, compass, ledger, matrix, pulse, strata, current
- Fixtures: 20; matches scheduled: 1260
- Primary provider: `stealth/space-bunny-alpha`; secondary: `codex`
- Primary errors: 0; secondary errors: 0

## Elo table (script output, verbatim)

```text
width | candidate | Elo | comparisons | W-L-T
--- | --- | ---: | ---: | ---
280 | pulse | 1724.50 | 120 | 98-16-6
280 | ledger | 1654.77 | 120 | 66-44-10
280 | strata | 1602.81 | 120 | 67-43-10
280 | beacon | 1579.03 | 120 | 65-41-14
280 | compass | 1483.28 | 120 | 57-57-6
280 | current | 1375.31 | 120 | 37-79-4
280 | matrix | 1080.30 | 120 | 3-113-4
320 | pulse | 1754.69 | 120 | 97-19-4
320 | ledger | 1666.99 | 120 | 71-37-12
320 | beacon | 1556.86 | 120 | 71-39-10
320 | compass | 1556.10 | 120 | 62-53-5
320 | strata | 1471.08 | 120 | 54-57-9
320 | current | 1414.09 | 120 | 40-78-2
320 | matrix | 1080.20 | 120 | 3-115-2
400 | pulse | 1773.11 | 120 | 97-20-3
400 | ledger | 1578.15 | 120 | 67-47-6
400 | compass | 1574.51 | 120 | 77-40-3
400 | beacon | 1537.67 | 120 | 68-45-7
400 | strata | 1501.89 | 120 | 50-64-6
400 | current | 1368.52 | 120 | 33-80-7
400 | matrix | 1166.15 | 120 | 11-107-2
```

## Width decisions

- `280px`: `no_candidate_beats_current`; best `pulse` (1724.50) vs current (1375.31), delta 349.19; final-family agreement=False.
- `320px`: `no_candidate_beats_current`; best `pulse` (1754.69) vs current (1414.09), delta 340.60; final-family agreement=False.
- `400px`: `no_candidate_beats_current`; best `pulse` (1773.11) vs current (1368.52), delta 404.59; final-family agreement=False.

## Human spot-check required

Open both referenced PNGs for each row and record `agree` or `disagree`, the deciding region, and why. A model verdict remains a claim until this table is completed.

Spot-check result: **10/10 machine-direction agreements** on the sampled first-glance/full PNG pairs.

| # | match | left glance | right glance | machine winner | confidence | human verdict | deciding region |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `320-dark-long-r06-m00-20260830_152450_0eaada-67` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/compass/320-dark/20260830_152450_0eaada-67.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/beacon/320-dark/20260830_152450_0eaada-67.glance.png` | right | 0.72 | **AGREE** | Beacon exposes the running status and NEEDS YOU heading sooner. |
| 2 | `280-light-medium-r08-m01-20260920_013343_700d78-306` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/compass/280-light/20260920_013343_700d78-306.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/pulse/280-light/20260920_013343_700d78-306.glance.png` | right | 0.93 | **AGREE** | Pulse's orange state cue and earlier NEEDS YOU separation make the waiting action salient. |
| 3 | `320-dark-long-r04-m02-20260830_152450_0eaada-67` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/compass/320-dark/20260830_152450_0eaada-67.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/strata/320-dark/20260830_152450_0eaada-67.glance.png` | right | 0.78 | **AGREE** | Strata's compact status-to-goal flow keeps RUNNING and the topic in the first glance. |
| 4 | `320-dark-long-r09-m00-20260903_124435_cd8638-129` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/strata/320-dark/20260903_124435_cd8638-129.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/beacon/320-dark/20260903_124435_cd8638-129.glance.png` | right | 0.98 | **AGREE** | Beacon labels the state and separates GOAL/DONE SO FAR; Strata's unlabeled opening blends status and bullets. |
| 5 | `400-dark-pivot-r00-m00-20260814_110332_5e05e2-15` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-z6q/renders/current/400-dark/20260814_110332_5e05e2-15.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/compass/400-dark/20260814_110332_5e05e2-15.glance.png` | right | 0.98 | **AGREE** | Compass puts the completed outcome before GOAL, while current spends the first block on the goal. |
| 6 | `280-dark-medium-r08-m02-20260814_000655_44953f-1` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/matrix/280-dark/20260814_000655_44953f-1.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/ledger/280-dark/20260814_000655_44953f-1.glance.png` | right | 0.99 | **AGREE** | Ledger preserves a readable single-column status; Matrix's split columns truncate WHERE THINGS STAND and bury the running sentence. |
| 7 | `280-dark-medium-r01-m00-20260818_124055_f80aaa-342` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-z6q/renders/current/280-dark/20260818_124055_f80aaa-342.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/beacon/280-dark/20260818_124055_f80aaa-342.glance.png` | right | 0.84 | **AGREE** | Beacon surfaces “work is finished” in the first status block; current delays it behind GOAL. |
| 8 | `320-light-pivot-r13-m02-20260814_110332_5e05e2-1` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/pulse/320-light/20260814_110332_5e05e2-1.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/strata/320-light/20260814_110332_5e05e2-1.glance.png` | right | 0.98 | **AGREE** | Strata puts the reviewer blocker in the leading status block and repeats the exact action under NEEDS YOU. |
| 9 | `280-light-long-r02-m01-20260903_124435_cd8638-129` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/pulse/280-light/20260903_124435_cd8638-129.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-z6q/renders/current/280-light/20260903_124435_cd8638-129.glance.png` | right | 0.94 | **AGREE** | Current makes the ABOUT WHAT answer immediate with GOAL first while keeping the completion/next-step status visible below. |
| 10 | `320-dark-handoff-r00-m01-20260822_231518_9853a4-50` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/strata/320-dark/20260822_231518_9853a4-50.glance.png` | `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/ledger/320-dark/20260822_231518_9853a4-50.glance.png` | right | 0.68 | **AGREE** | Ledger's explicit status heading, orange NEEDS YOU cue, and numbered action make the next step easier to locate. |

## Verified findings from losing designs

Complete only after the spot-checks. Each finding must name the losing candidate, fixture, PNG path, and visible region that proves the issue. Do not promote grader prose to a verified finding without opening the image.

- `matrix` — `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/matrix/280-dark/20260814_000655_44953f-1.glance.png`: the two-column layout truncates the state heading and wraps the status into a narrow rail, so the RUNNING cue is below the first-glance decision point.
- `current` — `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-z6q/renders/current/400-dark/20260814_110332_5e05e2-15.glance.png`: GOAL occupies the first block even though the truth is DONE; the decisive completed/deployed outcome is pushed below it.
- `compass` — `/Users/benjaminbrumbaugh/Documents/Hermes-Agent/temp/session-brief-eval/ha-dab/renders/compass/280-light/20260920_013343_700d78-306.glance.png`: the waiting state lacks the stronger orange treatment and the exact Time Machine action is lower than in Pulse, making WAITING ON ME slower to identify.

## Evidence limits

- Render manifests prove the real harness captured the requested panes and crops; they do not prove a user can answer the four questions.
- Elo depends on grader judgments and schedule coverage; it does not replace the human glance test.
- This run does not measure long-run auxiliary-call cost or non-English glanceability.
