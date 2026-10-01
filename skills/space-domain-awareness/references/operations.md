# Operational recipes

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`. These are working procedures with starting-point numbers for sparse optical deep-space data. Every threshold is [H] unless marked: re-tune it on the user's sensors and their cost of false alarms against misses (rule 5).

## 16. Operational recipes

### 16.1 Maneuver detection on sparse optical arcs

**Physics.** An impulse leaves position continuous and jumps velocity, so the pre- and post-burn trajectories intersect at the burn and their velocity difference there is the impulse. In Clohessy–Wiltshire terms a tangential burn gives a unique closest approach (separation ≈ ΔV·|t − t*|), a radial burn re-intersects every revolution and a normal burn every half revolution, so the epoch is ambiguous unless the search is confined to an observation gap shorter than half a period.

**Detector — "the observations stop fitting one ballistic orbit" [H]**
1. Keep the best published orbit. Refit on a shrinking window whose start never precedes the last maneuver-class event; advance the start in steps (≈6 h while the span exceeds ~5 periods, down to ~5 min as it shortens; coarser for dead objects) until the fit passes §16.2 or the span falls below ~30 min (active) or one period (dead).
2. Candidate when the best new arc begins after the best old arc ends (overlap allowance ≈15 min at GEO), or when an arc shorter than ~1.5 revolutions follows a published orbit. The pre-maneuver reference comes from the published-orbit history — never a GP element set and never a low-quality fallback: differencing heterogeneous orbit sources manufactures ΔV.
3. Characterize inside the gap [last pre-burn observation, first post-burn observation]: the minimum-ΔV two-impulse (Lambert) transfer bounds how cheap the change could be; the closest approach of the two orbits, searched only inside that transfer interval, gives the single-impulse epoch and ΔV, split radial / in-track / cross-track. Widen gaps under 60 min to 60 min (δr/Δt, §2); gaps over ~10 days are untestable.
4. Refit the post-burn arc with the pre-burn state propagated to the burn epoch as a prior whose velocity σ per axis is |ΔV_i| and position σ ≈ 50 s × σ_v; iterate epoch and ΔV while residuals improve.
5. Guards before publishing: ≥2 h of observations on each side (a full period for dead objects); evidence ratio ≥ ~20 observations per m/s of Lambert ΔV (40 observations allow ≤2 m/s, 200 allow ≤10 m/s); |ΔV| above a floor ≈0.025 m/s set from the orbit-difference noise of your own catalog (≈2σ for 100–200 m orbits — on a continuously refitted catalog this floor *is* the detector); burn younger than ~3 days; a ~3-day lookback against slot enter/exit flips from short arcs; a clean ballistic fit across the claimed epoch kills the claim.
6. Classify in element terms: drift change > ~0.01°/day (≈0.03 m/s); inclination change > 0.01° and > 5% of i (≈0.5 m/s; the relative test mutes naturally inclined objects); apsis change > ~10 km; begin/end drift and slot enter/exit; regime enter/exit (GEO, graveyard); station-keeping (not drifting on either side); otherwise generic.
7. Report: the epoch as a window bounded by the bracketing observations (precision ≈ σ_pos/ΔV, §2), ΔV with σ and RIC components, drift before → after and signed period change, post-burn σ, and the evidence — pre- and post-solve residuals on one panel.

**Tracklet-level kink test (cheap, real time).** Over ≤ ~17 min a GEO tracklet's angles are quadratic in time. Fit one quadratic and the best two-piece quadratic; split if the RMS ratio exceeds ~1.2, corrected for sample size (pure noise exceeds 1.2 for n ≲ 12). A burn is a kink — rates jump and the offset grows ≈ ΔV·t, visible only for ≳1 m/s; a cross-tag is a step with no intersection.

**Call maturation.** *Unexplained deviation* (residuals rising) → *potential maneuver* (a post-burn state exists but its σ is 200–300 m or worse, or one side has under 2 h of data: hold it and say "waiting on observations") → *maneuver* (gates met, full number set) → *confirmed* (post-event observations from a second sensor, or an operator ephemeris, §13.2). The post-burn σ tiers of §2 decide the step, not residual size. Every "potential" is closed out: confirmed, retracted, or absorbed into a thrusting state.

**Continuous and low thrust.** No impulse to find: it surfaces as persistent model mismatch (residual curvature, non-zero residuals after a refit) or a chain of small burns. Report a thrusting state with a drift-rate series and start/stop epochs, not one burn — a single-impulse summary of a 10-hour thrust arc misstates both ΔV and epoch. Multi-burn events get one record per burn with the chained drift (−0.6 → 0.0 → +0.6°/day), netted totals for nearly cancelling pairs, and the count.

**ΔV semantics.** A state-difference detector's ΔV is the 3-D velocity difference of two fits at the estimated epoch: it includes radial and cross-track components, fit error projected across the gap and timing error, and is routinely several times the along-track equivalent of the observed period change (1 s ≈ 1.2 cm/s, §2). The two are not interconvertible, and a ΔV without RIC components and σ cannot be checked against the element changes — quote it as an estimate, not a measurement.

**False-alarm taxonomy** (each guard above exists for one of these): wrong-root short-arc IOD → huge ΔV; window start leaking into pre-burn data → residual slope; unmodelled radiation pressure or attitude → residual curvature; sensor timing or bias → along-track offsets read as drift (§16.3); over-segmentation → drift-state flips on short arcs; empty or invalid element sets → garbage drift; heterogeneous orbit sources; burn epochs outside the gap; gaps dominating the span; cross-tags near neighbours and "maneuvering" dead objects (§16.4); stale re-alerts; continuous low thrust.

**Design note [CV].** Batch refits on shrinking windows are robust to sparse, irregular, biased data — no process-noise tuning, interpretable pre/post orbits, blacklist integration — at the cost of hours of latency (the ≥2 h post-burn arc), heavy CPU, and no calibrated false-alarm rate or ΔV covariance. The filter and control-distance methods of §6 supply the probabilities this does not; run both where latency matters.

### 16.2 Fit acceptance and publish gates

An orbit is published — used for prediction, screening and tasking — only when all of the following hold [H]:
- **Residual shape over the full arc *and* the last quarter orbit** (a burn or cross-tag at the end hides inside a full-arc RMS): RMS ≲ 2.5″, |bias| ≲ 3.5″, slope ≲ 5″/day, curvature ≲ 5–15″/day², Gaussianity fill factor ≥ ~0.65, and per-batch medians (≈75 observations) inside the same limits. Fill factor = (fraction of residuals within ±1σ) ÷ 0.6826, with σ from the 2.28%/97.72% percentiles: Gaussian 1.0, uniform 0.70, bimodal → 0, heavy tails > 1. Shape beats RMS: a fit forced across a burn, a cross-tag or a biased sensor shows bias, slope, curvature or bimodality before its RMS degrades.
- **Floors:** ≥ ~40 observations; effective span (span − largest gap) > ~3 h scaled by the period; σ_pos ≤ 2 km, with ceilings paired to observation counts (≈25 km only with ≥100 observations, 2.5 km with ≥50, 200 m with any); σ_pos ≲ 200 m for the tier that stops the shrinking window of §16.1.
- **Sources:** GP element sets are never pre/post references for a fitted orbit, and the orbit history records which fit owns which observation span.

**Editing (annealed, with a brake).** Centre on the median residual. Start the cut at 4× the floor — the tighter of the empirical RMS and the reported σ — then ×1.05 after a pass that removed points and ×0.5 after a clean pass; ramp the floor from 2σ to 4σ as the span grows from 1.5 to 3 revolutions (short arcs can afford tight editing, long arcs accumulate model mismatch). **If more than ~25% of the data would be rejected, undo the pass: the orbit is wrong, not the data** — restart from an initial orbit. Weight and test with the same σ; weighting with a fixed σ while testing with per-observation σ silently disables rejection.

**Thinning.** Dense tracks to ~500/day and 5/min while editing, ~2,500/day and 10/min for the final fit, always keeping endpoints: the information is in time diversity, not sample count.

**Initial orbits.** Grow the window to ≤4 h (6 h at most) with a line-of-sight sweep ≤90° and ≥5 min; a double-r grid over (R₁, R₃) finds every root as intersections of the two time-of-flight error curves; choose among roots with observations outside the triplet — a wrong root converges with plausible residuals and an implausible ΔV. Circular fallback: match the geocentric angular rate to the mean motion (two lines of sight constrain only a circular orbit); a single GEO look gives a circular orbit with i = |geocentric latitude|. Publish an IOD-based orbit only after ~2 h (active) or a full period (dead) of data.

**Priors and warm starts.** A catalog state enters as a pseudo-measurement with σ inflated by ~5 km + 5 km per day of age (cap 7 days) to allow for unseen maneuvers. Warm-start from the previous fit only when the new data fit it within ~3″ — warm starts over-weight old observations. Around a burn, use the inflated prior of §16.1.

**Covariance realism** (extends §6). The formal (AᵀA)⁻¹ with a fixed σ is unscaled: inflate it from the residuals, σ² ← σ_f² + f²·(σ_emp² − σ_f²) with σ_emp from (RMS² + bias² + slope²)/3 × range and a floor ≈30 m, and remember that altitude used as range understates GEO slant range. Use the growth curve of §2 for GP-class states. Sigma-point sets propagated through two-body dynamics are under-dispersive beyond a day. Never accept a zero covariance from a failed inversion. Solve for C_R·A/m only with ≥ ~3 days (active) or ~7 days (dead) of angles and never while drag acts — they alias.

### 16.3 Timing calibration and sensor-bias policy

**Facts [PS].** A geostationary line of sight turns at 15.04″/s against the stars (1″ ≈ 66 ms). Dec is the control channel: a clock error moves RA and leaves Dec alone, so σ_RA > σ_Dec means timing jitter, and a non-zero Dec median means a site, refraction, frame or truth-ephemeris error. Commercial camera stacks carry 0.3–0.45 s of latency (§2) — larger than any publish gate.

**Calibration recipe [H]**
1. Pair each detection with a known-ephemeris satellite in the same frames or the same night: SBAS/WAAS GEO broadcast ephemerides, GNSS precise orbits (IGS/MGEX, §4).
2. Search the latency over 0–1 s, coarse to fine, to 1 ms, minimising |median RA residual| per (sensor, target); for non-GEO truth project the residual onto the apparent along-track direction and divide by the rate. Allow negative values — a one-sided search cannot find an early time stamp.
3. Time tag = exposure start + t_exp/2 + latency; never (start + stop)/2 when "stop" includes readout. Resolve FITS time semantics explicitly (BEG/END midpoint, else start + t/2, else AVG, else OBS treated as mid — and record which).
4. Apply corrections as an idempotent, order-enforced state machine (none → shutter → aberration and light time), stored on the record (§12), with the measurement model declaring which state it expects. Never pre-correct light time with an assumed GEO range: the error at MEO is ≈14″.
5. Re-run after any hardware, focus, firmware or software change and whenever the sensor's residual drifts (§13.1).

**Bias policy — a self-healing blacklist [H]**
- Estimate per (target, sensor) the median residual over ~1.25 days after a publishable fit. Judge a sensor only when more than 4 clean sensors form a majority on that target, with ≥ ~100 observations/day, the suspect's data bracketed by clean data, and a 1.25–6 day span.
- Hysteresis: blacklist above ~1.5″ (≈100 ms), clear below ~0.5″ (≈33 ms).
- Global ban only when ≥4 targets have evaluated the sensor, more than ⅔ of them blacklist it and the median |bias| exceeds ~1.75″; the ban erases itself when the vote changes.
- **Always run one fit pass without the blacklist** (editing at ~4σ), then one with it (2–4σ): a sensor convicted by a bad orbit can only be exonerated by a fit that includes it.
- Pairwise relative bias — the difference of two sensors' median residuals on the same object within ~30 min — cancels orbit error and isolates the sensor.
- Exclude a biased sensor rather than correcting it; a correction hides the cause.
- A fixed per-observation σ (5–10 µrad) lets 1–2″ biases pass every rejection test; they bend orbits along-track, and a change in the sensor mix then looks like a maneuver (§16.1).
- RA gates ≈ 2× Dec gates (floors ≈1.8″ against 0.9″); an unknown latency defaults to ~0.3 s and is flagged.

### 16.4 Tracking and catalog correlation

**Gating angles-only data [CV].** χ² is 2-DOF in the tangent plane: χ² = tan²θ / tan²(atan(σ/ρ)), P = 1 − e^(−χ²/2). A scalar √trace σ gets χ² wrong by ~3× and ignores along-track elongation — gate with H·P·Hᵀ + R in the tangent plane. At GEO 0.1° of longitude is 74 km, and a day-old GP state with maneuver-inflated σ (~16 km ≈ 90″) makes every member of a co-located cluster ambiguous by construction.

**Two questions, two σ [H].** "Good match" uses the claimed object's own σ (accept P < ~0.97). "Unambiguous" uses every rival's σ inflated by ~5 km + 5 km per day of element age (cap 7 days) and requires the joint rival tail ≤ ~0.5%: rival tails multiply, so crowding adds up, and a diffuse rival vetoes a wide area unless its σ is capped. Ambiguous → uncorrelated track or deferral, never a forced tag.

**Frame-level association without an orbit model [H].** Project each line of sight onto the Earth-fixed GEO sphere (42,164 km): GEO objects become near-static points and association is clustering, with a linking length of ½ the star motion per frame (stars cannot chain) and a coast cap ≈120 s. Detections sharing a frame are a closely-spaced-object veto (both untagged, keyed per sensor and frame). Vote per cluster by purity: > 0.75 → catalog ID; 0.1–0.75, or ≥10 observations → uncorrelated track; else discard. Screen outliers against the *local median* residual, which is immune to stale-element bias. Minimum evidence ≥5 observations per dwell, re-checked after every rejection pass.

**Frame-to-frame tracker [H].** Constant-velocity Kalman filter in pixels (Joseph form, covariance clamps); global nearest neighbour by augmented Munkres with a private "new object" column per detection at the gate cost (χ²₂ ≈ 6, ≈95%), invalid pairs above the gate, and a time-boxed solver that fails closed and visibly; confirm at 3 hits, drop after 3 misses, terminate when σ_pos > ~5 px; pad σ for mount jitter; inflate σ for gating only, never for the update. Penalize a miss only when detection was geometrically possible (eclipse, phase, Earth limb, clouds). Merge tracks only when states *and* covariance shapes agree. Score tracks as recency- and sensor-diversity-weighted combined p-values.

**Catalog fusion [H].** Choose the source by freshness, σ and liveness: a proprietary fit yields to a GP set when stale (~1 day for active objects, ~5 for dead); the newest fit owns its observation span; deletions are tombstones; area-to-mass carries across sources. One policy, applied everywhere — several coexisting policies predict the same object from different element sets at different stages.

**Identity hygiene** (rule 10). Raw tags are immutable; corrections are patch overlays keyed by source, sensor, time and sky region. Recompute everything derived from an observation set when its links change — phantom "new object" alerts come from not doing so. Allocate uncorrelated-track numbers from one sequence (numbers that restart per sensor, run or cluster make one object many tracks) and keep ID ranges as a schema (public catalog, analyst 70,000–99,999, Alpha-5 100,000–339,999, internal blocks ≥ 10⁶), because the ranges collide. Identity errors feed straight into maneuver, anomaly and conjunction alerts.
