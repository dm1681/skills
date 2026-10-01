---
name: space-domain-awareness
description: Expert space domain awareness (SDA/SSA) engineering and analysis. Use when working with any satellite-tracking data - astrometry and photometry reduction, sensor calibration, orbit determination and propagation, TLE/OMM/CCSDS/UDL data, observation association, maneuver and anomaly detection, pattern of life, object fingerprinting, conjunction assessment, SDA data lake or ingestion pipeline design, and threat or intent assessments - even when SDA is not named.
version: 1.0.1
---

# Space Domain Awareness Engineering and Analysis

Guidance for SDA/SSA work at practitioner-to-expert level: reducing and calibrating observations, fitting and propagating orbits, associating tracks, detecting maneuvers and anomalies, fingerprinting objects, modeling pattern of life (PoL), designing the data pipelines underneath, and writing defensible assessments. Textbook orbital mechanics is assumed. This file holds the judgment, numbers and failure modes that are easy to get wrong.

**Sections** (1–2 below, 3–15 in `references/`): 1 Operating rules · 2 Quick numbers · 3 Sensors and observability · 4 Astrometry · 5 Photometry and characterization · 6 Orbit determination · 7 Propagation, frames, time · 8 Association and identity · 9 Pattern of life and anomalies · 10 Conjunctions · 11 Data standards and sources · 12 Pipeline and data lake design · 13 Decision playbook · 14 Lookup guide · 15 Landscape snapshot

## 1. Operating rules

The expertise that matters most in SDA is uncertainty discipline. Most "maneuvers" and "anomalies" in raw feeds are really timing errors, sensor bias, frame mix-ups, mis-tags, space weather or overconfident covariance, and each one looks like orbital behavior until it is ruled out. These rules keep them from reaching a conclusion or a table.

1. **Run every anomaly as a contest of hypotheses.** Rule out artifact, sensor error, mis-tag and force-model error before concluding a maneuver or a real change (§13.2). A wrong "maneuver" corrupts the object's PoL history and every model trained on it.
2. **Carry uncertainty and provenance end to end.** A measurement, orbit, feature or alert without an uncertainty and a source cannot be gated, fused or audited.
3. **State frame, time scale, units and epoch convention explicitly** in every schema, function signature and answer. Never infer them from context; silent defaults are the most common source of km-level errors. A documented schema default may be used only if it is recorded as a default and flagged.
4. **Keep observation, inference and assessment separate.** "Drift rate changed from 0.00 to 0.35°/day between two nights" is an observation. "A burn of about 1 m/s occurred in the daytime gap" is an inference. "The satellite is relocating to a new slot" is an assessment and carries a confidence level (§13.5).
5. **Label the authority of every rule or threshold** that will go into code or a decision: **[PS]** published standard, **[CV]** widely used convention, **[H]** heuristic to tune, **[C]** contested or uncertain. The [H] values here are starting points, not validated thresholds for the user's sensor network: say so, and recommend tuning against their data and their cost of false alarms versus misses. In an answer, say the label in words or give the legend once.
6. **Compute; do not estimate.** Closed-form arithmetic is fine for scale estimates. Frame and time conversions and propagation go through validated libraries (Orekit, astropy/ERFA, sgp4, skyfield), checked against a known case.
7. **Ask about the user's own system; never guess it.** Their schemas, sensor specifications, conventions, thresholds and data licenses are not in this file. Ask only the questions whose answers would change the result; otherwise state the assumption and proceed.
8. **Stay public and unclassified.** Work only from public sources. Do not speculate about classified capabilities. Do not put the user's proprietary or controlled data (sensor sites, raw observations, internal assessments, customer details) into web searches or external tools. If a task needs non-public information, stop and say so.
9. **Look things up when this file runs out** (§14) instead of filling gaps from memory.

**Answer shape.** Lead with the answer or decision, then the evidence, then only the caveats that could change it. Match length to the question: a quick question gets the verdict, the check or two that discriminate, and what would settle it. For a design request, lead with the decisions that drive the design. The rules above bind code, schemas and decisions in full; in a chat answer apply them silently and show frames, labels, provenance and caveats only where they change what the user does. Answer several independent questions one at a time in this shape.

## 2. Quick numbers

"Physics" rows are derived and can be recomputed; the rest carry a label or source (full citations in §14). Position figures use inertial speed; angle figures are what a ground sensor sees, so the two differ by the observer's own motion.

| Quantity | Value | Basis |
|---|---|---|
| Sidereal rate (stars vs a GEO-staring sensor) | 15.04″/s | physics |
| Apparent rate of MEO navigation satellites | ≈30–37″/s, about twice GEO | physics |
| 1″ on the sky | 4.85 m at 1,000 km; ≈180 m at GEO slant range | physics |
| Time error → along-track position | ≈7.5 m/ms LEO; ≈3.1 m/ms GEO | physics |
| Time error → angle at a ground sensor | GEO: 1″ per 66 ms; LEO at 0.5°/s: 1.8″ per ms | physics |
| Timing accuracy to aim for | ≤1 ms LEO; ≤10 ms GEO | [H] |
| Light time | ≈0.12–0.13 s at GEO (≈2″ if ignored); ≈3 ms at 1,000 km | physics |
| Annual / diurnal aberration | ≤20.5″ (≈3.7 km at GEO) / ≤0.32″ | [PS] |
| Refraction | ≈58″·tan z at standard conditions, z up to ~70° | [CV] |
| Site height wrong by 100 m | up to 21″ at 1,000 km range; 0.6″ at GEO | physics |
| UT1−UTC ignored (≤0.9 s) | ≈0.4 km at a ground site; ≈2.8 km at GEO radius | physics |
| TEME of date treated as J2000 | ≈0.37° in 2026: ≈45 km in LEO, ≈275 km at GEO | physics |
| J2000 (EME2000) vs GCRF | ≈0.02″ frame bias: negligible, but label which | [PS] |
| GPS time treated as UTC (18 s) | ≈137 km LEO; ≈55 km GEO | physics |
| TAI−UTC, GPS−UTC, TT−TAI | 37 s, 18 s, 32.184 s; no leap second through 2026 (IERS Bulletin C) | [PS] |
| Ground optical astrometry | ≈1″ RMS on small commercial telescopes; 0.5″ at good SNR on a 1 m | Gazak 2025; Schildknecht 2005 |
| GEO photometry | systematics ≲0.05 mag with a solar-color term; ≈0.1 mag RMS without | Chote 2025; Skuljan 2021 |
| Typical GEO brightness | V ≈ 11–14 | rule of thumb |
| GEO drift rate | 0.0128°/day per km of SMA offset; above GEO drifts west | physics |
| GEO ΔV ↔ drift rate | 2.84 m/s per 1°/day; 1 m/s along-track ≈ 27 km of SMA | physics |
| Along-track offset after an along-track burn ΔV | ΔV·[(4/n)·sin nt − 3t], n = mean motion. At GEO for 0.1 m/s, seen from the ground: +3.6″ at 3 h, zero near 5 h, −5.5″ at 6 h, −140″ at 24 h | physics |
| GEO slot geometry | a ±0.05° box is ≈74 km wide; co-located satellites keep kilometers apart, tens of arcsec or more on the sky | physics; [H] |
| GEO ΔV ↔ inclination | 53.7 m/s per degree | physics |
| GEO station-keeping budgets | north-south 41–51 m/s/yr; east-west up to ≈2 m/s/yr by longitude | [CV] |
| East-west burn; momentum dump | 0.05–0.2 m/s; 0.001–0.005 m/s | Decoto and Loerch 2015 |
| GEO deadband | ±0.05° typical, ±0.1° also common | [CV] |
| Daily GEO longitude libration | ±2e rad (e = 0.0002 → ±0.023°) | physics |
| Inclination without north-south control | ≈0.75–0.95°/yr, peaking at 15° after ≈26.5 yr of a 53-yr cycle | [CV] |
| Stable GEO longitudes | 75.1°E and 105.3°W; dead satellites librate about them | physics |
| IADC GEO disposal | perigee raised by 235 km + 1000·C_R·A/m (dry mass), e ≤ 0.003; ≥3°/day westward drift | [PS] |
| LEO ΔV ↔ SMA | ≈1.8 km per m/s at 550 km | physics |
| Area-to-mass | intact spacecraft and rocket bodies ≈0.005–0.1 m²/kg; high area-to-mass debris above ~1 | [H] |
| χ² 99% gates | 9.21, 11.34, 16.81 for 2, 3, 6 DOF | math |
| Thermosphere density error (1σ) | ≈15% NRLMSISE-00 class, ≈10% JB2008 when quiet; 25–35% or more in storms | [CV] |
| GP/TLE accuracy | km-level, no covariance (§7) | [C] |
| Conjunction Pc | 1E-7 attention, 1E-4 mitigation (§10) | [PS] |

## Section map

Read the reference file for a section before relying on it; `§` cross-references resolve here.

| § | Topic | File |
| --- | --- | --- |
| 3 | Sensors and observability | [`references/observations.md`](references/observations.md) |
| 4 | Astrometry | [`references/observations.md`](references/observations.md) |
| 5 | Photometry and characterization | [`references/observations.md`](references/observations.md) |
| 6 | Orbit determination | [`references/orbits.md`](references/orbits.md) |
| 7 | Propagation, frames, time | [`references/orbits.md`](references/orbits.md) |
| 8 | Association and identity | [`references/association-and-behavior.md`](references/association-and-behavior.md) |
| 9 | Pattern of life and anomalies | [`references/association-and-behavior.md`](references/association-and-behavior.md) |
| 10 | Conjunctions | [`references/association-and-behavior.md`](references/association-and-behavior.md) |
| 11 | Data standards and sources | [`references/data-and-pipelines.md`](references/data-and-pipelines.md) |
| 12 | Pipeline and data lake design | [`references/data-and-pipelines.md`](references/data-and-pipelines.md) |
| 13 | Decision playbook | [`references/decision-playbook.md`](references/decision-playbook.md) |
| 14 | Lookup guide | [`references/lookup-and-landscape.md`](references/lookup-and-landscape.md) |
| 15 | Landscape snapshot | [`references/lookup-and-landscape.md`](references/lookup-and-landscape.md) |
