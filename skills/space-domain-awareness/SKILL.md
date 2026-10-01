---
name: space-domain-awareness
description: Expert space domain awareness (SDA/SSA) engineering and analysis. Use when working with any satellite-tracking data - astrometry and photometry reduction, sensor calibration, orbit determination and propagation, TLE/OMM/CCSDS/UDL data, observation association, maneuver and anomaly detection, pattern of life, object fingerprinting, conjunction assessment, SDA data lake or ingestion pipeline design, and threat or intent assessments - even when SDA is not named.
version: 1.1.0
---

# Space Domain Awareness Engineering and Analysis

Guidance for SDA/SSA work at practitioner-to-expert level: reducing and calibrating observations, fitting and propagating orbits, associating tracks, detecting maneuvers and anomalies, fingerprinting objects, modeling pattern of life (PoL), designing the data pipelines underneath, and writing defensible assessments. Textbook orbital mechanics is assumed. This file holds the judgment, numbers and failure modes that are easy to get wrong.

**Sections** (1–2 below, 3–16 in `references/`): 1 Operating rules · 2 Quick numbers · 3 Sensors and observability · 4 Astrometry · 5 Photometry and characterization · 6 Orbit determination · 7 Propagation, frames, time · 8 Association and identity · 9 Pattern of life and anomalies · 10 Conjunctions · 11 Data standards and sources · 12 Pipeline and data lake design · 13 Decision playbook · 14 Lookup guide · 15 Landscape snapshot · 16 Operational recipes

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
10. **Check identity before inferring behaviour.** A maneuver, anomaly or conjunction computed on mis-tagged observations is wrong in a way no later step repairs: confirm the tag (orbit continuity, fingerprint, neighbours) before the call, and recompute everything derived from an observation set when its links change (§8, §16.4).
11. **Evidence must scale with the claim.** A large ΔV from few observations is a wrong orbit, not a maneuver; a published close approach needs a small σ; a short arc cannot flip an object's drift state. Budget the evidence per claim (§16.1) and hold the call until it is met.
12. **An orbit is valid only between maneuvers.** Never fit across a known burn, never screen a conjunction across one, and require observations after the closest approach before asserting a past encounter between active objects (§10, §16.1).
13. **Alert on contradiction, not on state.** Drifting, parked or tumbling is a state; severity rises when behaviour contradicts the object's design or declared status — a dead object holding attitude or maneuvering, an active one tumbling, a station-kept object with a periodic light curve (§9, §13.3).

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
| Period change ↔ drift, SMA, ΔV (GEO) | +1 s of orbital period ≈ 0.0042°/day westward ≈ 0.33 km of SMA ≈ 1.2 cm/s along-track; 1°/day ≈ 239 s ≈ 78 km ≈ 2.84 m/s | physics |
| Osculating period at exact GEO | reads ≈ −0.027°/day of drift because J2 lifts the osculating SMA ≈ 1.6 km; treat \|drift\| < 0.03°/day as station-keeping noise | physics; [H] |
| Natural change of a GEO drift rate | ≤ ≈0.002°/day² from the tesseral field (≈0.014°/day per week); a larger week-to-week change is estimation noise or thrust | physics |
| Camera latency at GEO | 0.3–0.45 s is common for commercial camera stacks ≈ 5–7″ along-track ≈ 1–1.3 km, larger than any publish gate: calibrate per sensor (§16.3) | [H] |
| Solar radiation pressure at GEO | a ≈ 4.6e-6·C_R·A/m m/s²; C_R·A/m = 0.02 forces e ≈ 2.2e-4, a ±19 km daily longitude libration; ≥3 days of angles separate it from state error | physics; [H] |
| Along-track error growth of a fresh optical GEO fit | ≈×1.5 at 1 h, ×7 at 5 h, ×20 at 10 h, ×30 at 24 h, then ≈×30 per day; 1 km of SMA error ≈ 9.5 km/day | [H]; physics |
| Burn epoch and fake ΔV | epoch precision ≈ σ_pos/ΔV (100 m at 0.1 m/s ≈ 17 min; at 1 m/s ≈ 100 s); differencing two orbits across a short gap manufactures ΔV ≈ δr/Δt (1 km over 10 min ≈ 1.7 m/s; over 60 min ≈ 0.3 m/s) | physics |
| GEO brightness vs geometry and size | diffuse-sphere phase function 0.88 at 30°, 0.61 at 60°, 0.32 at 90°, 0.11 at 120°; real GEO comsats fade ≈4 mag from 0° to 120°; diameter ≈ 12.8 m·2^−(V−9)/1.5 at zero phase (diffuse, albedo ≈0.25; good to ~2×) | physics; [H] |
| Evidence per maneuver claim | ≥ ≈20 post-event observations per m/s of claimed ΔV before publishing (§16.1) | [H] |
| Post-burn state σ tiers (optical GEO) | ≲100 m solid; 200–300 m "high" — hold as a candidate; ≳1 km wait for more observations (§16.1) | [H] |
| Disposal and kick-motor drift | graveyard ≈ −6.8°/day westward (≈530 km above GEO); GEO apogee kick motors ≈ −3.3 to −3.9°/day (≈260–300 km above) for years | physics; [H] |
| Earth seen from the object | from GEO: angular radius 8.7°, 0.072 sr; visible earthshine ≤ ≈0.5% of sunlight (≈ −5.8 mag) and zero at the object's local midnight; from 550 km: ≈25% (≈ −1.5 mag); Earth-albedo and infrared radiation pressure ≈0.5% and 0.4% of SRP at GEO | physics |
| Optical limiting magnitude vs geometry | ≈13 at 30° solar elongation rising to ≈19 at 60°; ≈13–15 with the Sun at −10° to ≈18 at −20°; keep >20° from the Moon, which costs 1–2 mag near full | [H] |
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
| 16 | Operational recipes | [`references/operations.md`](references/operations.md) |
