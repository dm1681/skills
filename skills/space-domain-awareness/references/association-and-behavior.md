# Association, pattern of life and conjunctions

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 8. Association and identity

- **Gating:** d² = νᵀS⁻¹ν against the 99% χ² value for the measurement dimension (§2) [CV]. A gate is only as good as S: overconfident covariance produces false uncorrelated tracks, inflated covariance produces mis-tags.
- **Ambiguity:** with more than one candidate in the gate, defer (multiple hypothesis tracking or multi-frame assignment) or carry association probabilities. Forced nearest-neighbor assignment in clusters creates cross-tags.
- **Provider tags are claims.** Store a provider's or tasking system's object ID on the observation as an asserted ID and run your own association.
- **Uncorrelated tracks:** tracklet → admissible-region linking across nights → initial orbit → full fit. Promote to a new object only with a consistent multi-night orbit and no catalog object in the gate; at GEO require at least two nights [H].
- **Cross-tags** are endemic in co-located GEO clusters and LEO deployment trains. Signature: two neighbors show simultaneous "maneuvers" of opposite sense, and swapping the tags removes both. Resolve with orbit continuity plus an independent fingerprint (photometry, RF) before any maneuver call. Scale check [H]: co-located satellites keep kilometers apart, so a true cross-tag produces residuals of tens of arcsec or more; an offset of a few arcsec is more likely a blend, a time bias or a real burn.
- **Breakups, launches, deployments:** use temporary IDs and expect identities to settle over days to weeks. Do not build PoL on unsettled identities.
- **Identity model:** many-to-many, time-versioned links between catalog number, international designator, provider IDs and uncorrelated-track IDs, each with a probability and method. Keep history; public catalog identities get corrected retroactively.
- **Catalog numbers.** The 5-digit range (1–69999) ran out on 2026-07-11 and new objects are numbered 100000 and up (CelesTrak). What a TLE feed does now depends on the provider: CelesTrak issues no TLE for those objects; Space-Track's gp and gp_history classes emit Alpha-5 in TLE/3LE output (first character a letter, A = 10 … Z = 33, no I or O: 100000 → A0000, 148493 → E8493, 339999 → Z9999); Space-Track's legacy TLE classes stay 5-digit. Every other format carries an integer up to 999,999,999, which fits in int32. So: ingest OMM, key on the integer, decode Alpha-5 explicitly where TLEs must be read, and keep the ID in your own column, because some SGP4 libraries reject numbers above 339999. Naive parsers fail silently (NaN, 0 or dropped sets). Analyst numbers 80000–89999 are reused for different objects: one more reason a catalog number is an attribute in the identity table, not a key.

## 9. Pattern of life and anomalies

**Baselines**
- *GEO, controlled:* the east-west cycle is a longitude parabola inside the deadband with burns near the edge, from weekly to every couple of months for chemical propulsion and near-daily for electric. North-south burns hold the inclination vector. Momentum dumps are tiny.
- *GEO, inclined or fuel-saving:* no north-south control; inclination grows at the natural rate.
- *GEO relocation:* drift orbit above (westward) or below (eastward) GEO, then a stop burn. ΔV follows §2.
- *GEO end of life:* raise to the disposal altitude, drift west at 3°/day or more, then tumble after passivation. Dead in place: libration about a stable longitude, inclination growth, tumbling light curve.
- *LEO:* orbit raising (staircase or continuous), phasing, drag make-up that scales with solar activity, collision avoidance, controlled deorbit or natural decay. Judge each constellation member against its plane or shell peers; the anomaly is the outlier (failed to raise, decaying, out of slot).
- *MEO:* navigation satellites maneuver rarely; a maneuver is itself notable.

**Features worth materializing per object:** SMA and drift rate; longitude and deadband occupancy; inclination and eccentricity vectors; maneuver events (epoch, ΔV, radial/transverse/normal direction, confidence, evidence); inter-maneuver intervals; photometric state (stable or tumbling, period, phase-curve parameters, glint offset); RF activity; proximity events (range, relative velocity, geometry, duration); and context flags (coverage gap, storm, season, data quality).

**Methods**
- Change-point detection (PELT, Bayesian online, CUSUM) on element time series; mode labeling in the style of MIT ARCLab's SPLID benchmark (east-west and north-south nodes for initiate station-keeping, initiate drift and adjust drift; modes of not station-keeping, or station-keeping with chemical, electric or hybrid propulsion; scored with F2 at ±12 h tolerance).
- Sequence models (hidden Markov, transformers) and unsupervised detectors (isolation forest, autoencoder) on engineered, physics-aware features, not raw elements.
- An anomaly is a deviation from the object's own baseline and from its peers, normalized by uncertainty and conditioned on context.
- Evaluation: labels are scarce, so use operator-published maneuvers and ephemerides as truth, synthetic injection and historical replays. Split by time, build features point-in-time (§12), and pick the metric from the cost: F2 when misses cost more, precision at a fixed alert budget for an analyst queue.

**Public case signatures**
- Docking or servicing: photometric fingerprint change (MEV-2 and Intelsat 10-02).
- Tug: a large, unannounced orbit change of a dead object. SJ-21 docked with a defunct BeiDou satellite during a daytime gap in ground optical coverage and towed it about 3,000 km above GEO (January 2022).
- Serial inspector: repeated relocations ending tens of km from other operators' satellites (Luch/Olymp-K and Luch/Olymp 2).
- Sub-satellite release and matched-plane shadowing of another satellite, then release of a further object (Cosmos 2542/2543, 2019–2020).
- Paired inspectors bracketing a target (commercial tracking analysis reported this for GSSAP around Shijian-29 A/B, March 2026).

**Deception-aware detection [H].** Expect maneuvers timed to coverage gaps, object swaps or decoys during a custody gap (COMSPOC's analysis of TJS-3 and its kick motor, May 2019), maneuvers masked by storms, and behavior that mimics benign servicing. After any custody gap with a position discontinuity, re-verify identity before extending PoL.

## 10. Conjunctions

- 2D probability of collision (Foster, Chan, Alfano, Patera) assumes a short, high-relative-velocity encounter with Gaussian position error. Slow or long encounters (GEO neighbors, formations, proximity operations) need 3D or Monte Carlo methods [CV].
- Pc is a function of covariance realism. An oversized covariance dilutes Pc; a low Pc in the dilution region is not evidence of safety [C]. Never compute Pc from GP/TLE states.
- **NASA [PS]** (NPR 8079.1; Conjunction Assessment Best Practices Handbook Rev 2, August 2026): Pc above 1E-7 merits attention. The mitigation threshold is Pc above 1E-4 at the mitigation commitment point, or a miss distance below the combined hard-body radius. A mitigation should cut Pc by at least 1.5 orders of magnitude (to about 3E-6).
- **19th Space Defense Squadron [PS]** (Spaceflight Safety Handbook v1.7, April 2023). Conjunction messages are published for near-Earth events (period under 225 min) with closest approach within 3 days, miss ≤1 km and Pc ≥1E-7, and for deep-space events within 10 days and ≤5 km. Emergency criteria: near Earth within 3 days, miss ≤1 km and Pc ≥1E-4; deep space within 3 days and ≤5 km. Catalog screening volumes (radial × in-track × cross-track, km): 0.4 × 44 × 51 for perigee ≤500 km, stepping down to 0.4 × 2 × 2 for 1,200–2,000 km; 10 × 10 × 10 in deep space. Operator-ephemeris screening uses 2 × 25 × 25 near Earth and 20 × 20 × 20 in deep space. Read the handbook tables before implementing.
- Thresholds are the operator's risk policy, not a constant; some operators act orders of magnitude below 1E-4. Make them per-customer configuration.
- Store the Pc method, hard-body radius (Pc scales roughly with its square) and covariance age with every value. A missing Pc means not computed, not safe: fall back to miss distance.
- Check a conjunction message before acting on it: age of the last observation, number of tracks, covariance plausibility, and whether the other object is maneuverable or has an operator ephemeris.
