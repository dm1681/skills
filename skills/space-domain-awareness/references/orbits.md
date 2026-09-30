# Orbit determination, propagation, frames and time

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 6. Orbit determination

- **Initial orbits:** Gauss for short angles-only arcs, Double-R or Gooding for longer ones, Gibbs/Herrick-Gibbs or Lambert with range. A single tracklet supplies only four numbers (angles and rates); use admissible regions (Milani; Tommei; DeMars, Jah and Schumacher) and link tracklets across nights instead of forcing an orbit from it.
- **Estimator:** batch least squares for catalog maintenance and forensic reconstruction; a sequential filter with smoother for real-time custody and maneuver detection.
- **Solve-for set:** LEO: state plus ballistic coefficient. GEO/HEO: state plus solar-radiation-pressure coefficient. Estimate sensor biases from calibration satellites, not from the target, where they alias into the orbit.
- **Process noise:** filters need non-zero process noise (state noise or dynamic model compensation) or the covariance collapses. Batch formal covariances ignore model error and are optimistic for the same reason.
- **Editing [CV]:** iterative 3σ editing on normalized residuals, logged as flags. A run of consecutive rejected observations with the same sign is a signal (maneuver or mis-tag), not noise.
- **Fit span [H]:** LEO 1–7 days depending on drag; MEO/GEO 7–30 days, with several nights for optical-only GEO. Never straddle an unmodeled maneuver.
- **Fit quality:** weighted RMS near 1 when the noise model is right; well above 1 means unmodeled dynamics or understated noise. Residuals should be white: check mean, trend and per-sensor structure.
- **Around a maneuver:** known epoch, segment the fit there; small continuous thrust, add process noise or an empirical acceleration; large unknown maneuver with custody lost, restart from an initial orbit.

**Covariance realism [CV]**
- Test: compare predictions with later truth or a better orbit. d² = Δxᵀ P⁻¹ Δx should follow χ² with n DOF (3 for position, 6 for state), so its mean is near n. Test the empirical distribution with Cramér-von Mises or Kolmogorov-Smirnov. For filters, check normalized estimation error (NEES ≈ n) and innovation (NIS ≈ measurement dimension).
- Fixes: tuned process noise, consider parameters for drag, solar radiation pressure and bias, and empirical scale factors that are specific to regime and propagation time [H].
- Trust a covariance only when it passes these tests on recent history for that object class and data source [H].
- Propagated in Cartesian coordinates, a Gaussian bends along the orbit as along-track uncertainty grows, within an orbit or two for poorly known objects. Use equinoctial or curvilinear coordinates, Gaussian mixtures or sigma-point methods for longer spans.
- GP/TLE element sets carry no covariance. Estimates from differencing consecutive element sets measure self-consistency, not accuracy. Covariances delivered without process noise can be badly overconfident.

**Maneuver detection methods [CV]:** windowed innovation χ² tests; interacting multiple model or variable-state-dimension filters; control-distance metrics (Holzinger, Scheeres and Alfriend 2012: the minimum ΔV that connects the old state to new observations, compared with what uncertainty alone explains); change points in SMA or drift rate (east-west) and the inclination vector (north-south). Low thrust has no discontinuity: estimate an empirical acceleration over sliding windows and compare it with solar-radiation-pressure uncertainty.

## 7. Propagation, frames, time

**GP data (TLE, OMM)**
- The elements are SGP4 mean elements. Propagate them only with SGP4; the output frame is TEME. Never treat them as osculating or feed them to a numerical propagator.
- Ephemeris type 4 in a USSF element set marks SGP4-XP: it needs the SGP4-XP library, the drag and second-derivative fields change meaning, and mixing either way gives very poor results (Payne et al., AMOS 2022).
- Convert TEME with a library implementation that follows Vallado et al. 2006 (AIAA 2006-6753).
- Limits: no covariance; element sets lag a maneuver by days and smear it; B* absorbs fit error and is not a physical drag term (it can be negative).
- Accuracy [C]: published figures bracket it loosely. Intrinsic SGP4 fit error alone is 0.1–0.5 km along-track for LEO, MEO and GEO and 1.4–3.9 km for HEO and GTO (Flohrer et al. 2008, a lower bound). Against laser-ranged truth, four geodetic satellites showed 0.8 km at epoch growing about 1.5 km/day, with 0.1–3 km/day across the literature (Levit and Marshall 2011). In one CelesTrak test GPS element sets averaged 7.5 km against 0.9 km for operator-derived SupGP. Measure it on the user's own objects before relying on a number.
- GP is adequate for visibility, tasking and coarse screening. Probability of collision, maneuver characterization and proximity geometry need special-perturbations or operator ephemerides [CV].

**Numerical propagation: force model by regime [CV]** (Vallado, AAS 01-429; USSF conjunction-message metadata)
| Regime | Model |
|---|---|
| LEO | gravity 36×36 (USSF catalog practice) to 70×70 (Vallado), drag with an empirical density model and solved ballistic coefficient, lunisolar, solar radiation pressure, solid tides |
| MEO | gravity up to 40×40 for high accuracy, lunisolar, solar radiation pressure |
| GEO | gravity 8×8, lunisolar, solar radiation pressure with solved coefficient |
| HEO / GTO | LEO-class gravity and drag at perigee plus third-body |
| Cislunar | full-ephemeris n-body; no Keplerian elements or TLEs; CR3BP for intuition only |

**Drag and space weather**
- Density error dominates LEO prediction (§2). Record which model and which indices (observed or predicted F10.7, Kp/ap, Dst) each run used.
- In a geomagnetic storm (NOAA G-scale: Kp 5 = G1 through Kp 9 = G5 [PS]) the whole LEO catalog shifts at once. In May 2024 forecasts under-predicted the storm, decay rates jumped catalog-wide and nearly half of active LEO satellites maneuvered together (Parker and Linares 2024). During storms: widen gates, inflate LEO process noise, suppress per-object maneuver alerts that match population-wide residual growth, and tag features as storm-affected.

**Frames and time**
- GCRF for inertial states; ITRF for sites; TEME only for SGP4 input and output. Use the IAU 2006/2000A reduction with IERS Earth orientation parameters.
- Earth orientation parameters and space-weather indices come as predictions that are later replaced by final values. Record the version used, or the run cannot be reproduced.
- The size of each classic mistake is in §2. Add polar motion ignored (≈10 m) and a stale leap-second table.

**Software.** Adopt validated libraries for frames, time and propagation and build only the domain layers: Orekit (broadest open-source orbit determination and propagation), astropy with ERFA, sgp4 (Vallado reference), skyfield, GMAT, Tudat, Basilisk; commercial STK/ODTK and FreeFlyer. Validate any pipeline against one of them on known cases.
