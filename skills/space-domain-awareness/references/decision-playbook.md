# Decision playbook

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 13. Decision playbook

### 13.1 Data-level decisions
| Decision | Evidence | Rule | If wrong |
|---|---|---|---|
| Accept or reject an observation | normalized residual, SNR, flags | edit above 3σ [CV]; flag, never delete | real maneuver evidence is thrown away |
| Object or artifact | persistence across frames, motion, PSF shape | at least 3 detections on consistent motion [H] | cosmic rays and hot pixels become tracks |
| Photometry usable | saturation, blending, sky transparency, zero-point scatter | zero-point scatter ≲0.05 mag for fingerprinting [H] | weather is read as a change in the object |
| Re-estimate sensor bias | bias trend on calibration satellites | drift beyond 1σ of the estimate, or any hardware or software change [H] (recipe in §16.3) | phantom maneuvers across every object that sensor sees |
| De-weight or exclude a sensor | its residual RMS against its claimed noise | weighted RMS persistently above ~2: inflate its noise first, exclude last [H] | coverage lost for nothing, or bad data trusted |
| Blacklist a sensor | its median residual per target against a clean majority of sensors | hysteresis ≈1.5″ on, ≈0.5″ off; global ban only on a supermajority of targets; always refit once without the list [H] (§16.3) | a bad orbit permanently convicts a good sensor, or a biased one keeps bending orbits |

### 13.2 Is it a maneuver?
Carry every hypothesis the evidence has not excluded; do not stop at the first that fits. Status moves from *unexplained deviation* to *candidate maneuver* to *confirmed maneuver*.

0. **Context first.** Season (glint season saturates and blends centroids; eclipse season opens gaps), space weather, coverage gaps, and whether the detector's flag rests on the same observations. If it does, it is not independent evidence.
1. **One sensor or all?** A deviation at one sensor while another observing at the same time looks nominal points to sensor bias, timing or bad data. A nominal second sensor clears the object only if it observed during or after the deviation.
2. **Timing?** Look at the same frames first: slot-mates and other objects at that sensor share the time tag. The same along-track offset on all of them, larger on faster calibration satellites, is a time bias. A tagging or latency error is a constant step, whereas a burn's offset follows the orbit: it grows, reverses sign about 5 hours after an along-track burn at GEO, and reaches arcminutes by the next night (§2).
3. **Mis-tag or blend?** In a cluster: does swapping tags remove the deviation on both objects, is the photometric or RF fingerprint continuous, are the detections cleanly separated?
4. **Space weather?** In LEO during a storm, compare with residual growth across objects at similar altitude and ballistic coefficient. Common-mode growth is drag error.
5. **Force model?** Slow, smooth growth at GEO/HEO suggests a change in solar radiation pressure or attitude, or a high area-to-mass object.
6. **Breakup or deployment?** New uncorrelated tracks nearby, or a photometric change.
7. **Otherwise a candidate maneuver.** Fit pre- and post-event orbits separately, estimate epoch and ΔV, and test plausibility against the object's history and class (size, direction, timing relative to its cycle). Detector, guards and false-alarm list in §16.1; hold the call as *potential* while the post-burn σ is 200–300 m or worse or either side has under 2 h of data (§2), and close every potential out explicitly.
8. **Confirm** with an independent sensor or modality, an operator ephemeris, or a post-event fit that converges with realistic covariance at more than one site. Require two independent sources before "confirmed" [H].

Until it is resolved, flag the suspect observations and keep them out of the orbit fit and the maneuver history. Never delete them.

### 13.3 Anomaly triage [H]
- Score = deviation from the object's own baseline and peers, normalized by uncertainty, conditioned on space weather, coverage and data quality.
- Rank by asset criticality × severity × proximity to high-value assets × confidence.
- Merge correlated alerts (a storm, a sensor outage, a cluster re-tag) into one event.
- Request follow-up collection before reporting whenever confidence is below moderate and time allows.

### 13.4 Characterization and identity [H]
- *Active:* station-keeping seen within about twice the object's median maneuver interval, or stable-attitude photometry.
- *Dead:* control stops, inclination grows at the natural rate, longitude drifts toward a stable point, light curve becomes periodic.
- Declare a status change only when it persists across at least two geometry-matched collections.
- A photometric change is *confirmed* only when two sensors see it, or the same sensor sees it at the same time of night on two nights; a single-sensor, single-night change is "not confirmed", stays an open thread, and is closed explicitly — back to baseline, confirmed, or re-baselined as persistent variability [H]. Changes at the edges of the observing window, or recurring at the same clock time on unrelated objects, are geometry or a sensor hand-off until phase-matched (§5, §9).
- Identity attribution needs two independent lines of evidence (orbit continuity plus photometric or RF fingerprint) whenever the object has been through a custody gap or a cluster.

### 13.5 Threat, intent and tradecraft
- **Indicators to report as observations:** approach within tens of km of another operator's GEO asset; persistent co-location or drift matching; repeated passes with the Sun behind the approaching object; maneuvers timed to coverage gaps; synchronized maneuvers by paired objects; release of sub-objects; a change in RF or photometric state coincident with proximity.
- **Describe relative motion precisely:** range, range-rate, duration, geometry (circumnavigation, fly-by, hold), lighting. The full reporting form for a close approach is in §10.
- **Reason as capability × opportunity × intent.** Intent is almost never observable. Keep it as an assessment with alternatives stated (inspection, servicing, debris removal, testing, relocation, collision avoidance). Commercial servicing and inspection look the same in the data as counterspace rehearsal [C].
- **ICD 203 estimative terms [PS]:** almost no chance 1–5%; very unlikely 5–20%; unlikely 20–45%; roughly even chance 45–55%; likely 55–80%; very likely 80–95%; almost certain 95–99%. Confidence (high, moderate, low) rests on source quality and corroboration and must not share a sentence with a likelihood term.
- **When to use them.** Estimative terms are for assessments of what an object did or will do, and only when the supporting evidence can be named. Routine data-quality triage needs a verdict and the discriminating check, not a probability.
- **Competing hypotheses:** list them, weigh evidence by how well it discriminates (evidence consistent with every hypothesis is worth nothing), and try to refute instead of confirm. Guard against anchoring on the first "maneuver" label, mirror-imaging the other operator, and deferring to the detector's output.
- **Sourcing:** say which sensors and providers, the data quality, and what is assumed.

### 13.6 Tasking [H]
- Priority: protect high-value assets and confirm suspected maneuvers, then recover lost custody, then maintain the catalog, then survey.
- Choose by expected information gain: covariance reduction, time since last observation against error growth, geometric diversity (a different site beats more from the same site), and modality.
- Revisit often enough that propagated uncertainty stays inside both the association gate and the sensor field of view; maneuvering and high-interest objects need more.
- Lost custody: propagate the last good state with inflated covariance, search along-track first, then the set reachable with a plausible ΔV (at GEO, 1 m/s ≈ 0.35°/day of drift), then the operator's other slots.

### 13.7 Thresholds and decision theory
- Set alert thresholds from costs. Alert when the likelihood ratio exceeds (cost of false alarm × prior of no event) ÷ (cost of miss × prior of event). With rare events the base rate dominates: report precision at the expected event rate, not only ROC curves.
- Fixed analyst capacity: fix the false-alarm rate and maximize detection (Neyman-Pearson). Accumulating evidence: sequential probability ratio test, accept the event at LR ≥ (1−β)/α and reject at LR ≤ β/(1−α).
- Collect more when the expected reduction in decision loss exceeds the cost and delay of collection.
- Show the evidence and the alternatives with every automated call so an analyst can check it.

### 13.8 Engineering trade-offs [H]
- Physics first for anything operator-facing; machine learning for ranking, screening and feature extraction; physics residuals as model features for PoL.
- SGP4 for catalog-wide screening and tasking; numerical propagation for decisions.
- Before operational use: regression against GNSS and laser-ranging truth, historical replays (the May 2024 storm, known maneuvers), covariance realism metrics, and round-trip tests for frame and time conversions.
- Any change in calibration, reference data or algorithm triggers selective reprocessing under a new version tag.
