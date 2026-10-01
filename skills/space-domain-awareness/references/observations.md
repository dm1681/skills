# Sensors, astrometry and photometry

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 3. Sensors and observability

| Modality | Measures | Best for | Limits |
|---|---|---|---|
| Ground optical, wide-field (sidereal or GEO-stare) | angles, brightness | GEO/MEO/HEO custody; photometry comes free | night and weather; no range; short arcs |
| Ground optical, narrow-field rate-track | angles, high-SNR light curves | characterization, faint objects | tasking-limited |
| Daytime / SWIR optical | angles in daylight | closing the daytime custody gap on bright objects | sky background |
| Event-based cameras | asynchronous brightness changes, µs timing | LEO streaks | calibration immature [C] |
| Radar (phased array, tracking, ISAR) | range, range-rate, angles, RCS, images | LEO; all-weather; direct range | R⁻⁴ sensitivity |
| Passive RF (TDOA/FDOA) | emitter location, frequency, modulation | active GEO; day and night; RF fingerprint | emitters only |
| Space-based optical | angles, resolved images | no weather; favorable geometry | cost; scarce tasking |
| Satellite laser ranging | mm–cm range | calibration truth | retroreflector targets only |
| Polarimetry, spectroscopy, multi-color | material and bus discrimination | GEO characterization | low SNR; hard calibration |

- **Angles-only short arcs** leave range and range-rate unobservable. One GEO night fixes longitude well and drift rate (SMA) poorly; a second night, or an arc of hours, is what constrains it.
- **Radar range-rate** pins LEO along-track state and drag. Optical dominates deep-space catalog maintenance.
- **Coverage gaps are structural, not anomalous:** daylight and weather for ground optical; lunar exclusion; GEO eclipse seasons (about 6.5 weeks centered on each equinox, up to ~72 min per night near local midnight). A maneuver inside a gap shows up as a position discontinuity afterward.
- **An independent modality is worth more than more of the same.** RF and photometric signatures are identity evidence that does not depend on the orbit.
- Treat vendor performance claims without published validation as [C].

## 4. Astrometry

**Reduction chain [CV]**
1. Bias, dark and flat calibration; mask hot pixels and cosmic rays.
2. Background estimation that handles Moon and twilight gradients.
3. Detection of points or streaks according to track mode (sidereal: target streaks; rate-track: stars streak; GEO-stare: stars streak, GEO objects are points).
4. Centroiding: PSF fit for points, trailed-PSF fit for streaks. Record whether the position is the streak midpoint or an endpoint, and the time it corresponds to.
5. Plate solution against Gaia DR3 with proper motion propagated to the observation epoch, plus a distortion model (SIP/TPV). Store the WCS and the star residual RMS.
6. Target pixels → RA/Dec with a per-observation uncertainty from centroid and plate-solution error. State whether the RA sigma is on-sky (× cos δ), carry the RA–Dec correlation for streaks, and keep time uncertainty in its own field, saying whether the angular sigma already includes angular rate × time sigma.

**Frame calibration and the noise model [CV unless marked]**
- *Master frames:* bias from overscan or zero-exposure medians; darks scaled by exposure *and* temperature (dark current roughly doubles every 6–7 °C, so exposure-matched darks alone leave hot-pixel residue that detects as objects); flats per filter and binning through the same optical path, refreshed after refocus or dust (a stale flat leaves 1–5% and the vignetting error of §5); thinned CCDs need a fringe frame in the red.
- *Pixel masks:* hot, warm and dead pixels from dark statistics; a row or column is bad when >20% of its pixels sit beyond 3σ; amplifier glow and vignetted corners masked by geometry; saturation flagged at ~95% full well for detection, with the lower photometric limit of §5. Single-frame cosmic rays and hot pixels fail a PSF-consistency (spike) test — centre pixel against the flux the wings imply — so no second frame is needed [H].
- *Background:* real-time pipelines often skip dark and flat and rely on a robust background: block medians (~64 px) with a percentile σ ((x84 − x16)/2 or x84 − median), bilinear interpolation, flagged pixels excluded, σ never zero. A block model removes only structure larger than ~2 blocks: Moon and twilight gradients need it, a constant will not do, and blocks smaller than the largest star halo eat flux.
- *Noise model per pixel:* σ² = read² + I/gain + (m·I)², where the multiplicative term (~1–2% flat and PSF error) keeps bright stars from failing residual tests and sets the photometric floor; include the Poisson term for sky and target (a model without one is overconfident at the faint end); measure gain from a photon-transfer curve *after* removing read noise and fixed pattern, or it comes out low and every SNR high.
- *Fixed-pattern noise:* two-point non-uniformity correction for CMOS and infrared arrays; row and column structure by 1-D median filtering; after subtraction verify that the residual background has zero median and the σ the photon-transfer curve predicts, and that star residual RMS and zero-point scatter are flat across the field.
- *Threshold calibration:* run the detector on noise-only frames, because background subtraction correlates the noise: a matched filter reaches 50% completeness ≈0.4 SNR below its nominal threshold and a peak-pixel gate needs ≈1.2×threshold/EOD; set the gate from the false-alarm budget (6σ ≈ 0.02 false detections per 16 Mpx frame; 5σ ≈ 5 per 4k² frame) [H].

**What star-relative astrometry does and does not remove**
- Star-relative positions are *astrometric* places: comparable with catalog star positions. Refraction cancels against the stars to first order.
- **Annual aberration does not cancel.** The stars are displaced by up to 20.5″ from their catalog places; an Earth satellite's geocentric direction is not. An astrometric place therefore differs from the direction an orbit-determination program computes in GCRF (station at receive time, object at emit time) by the annual aberration, evaluated with the geocenter's barycentric velocity at the object's position. Apply it exactly once: add it to the observation at reduction (it moves the place toward the apex of Earth's motion), or remove it from the computed direction in the measurement model. Record which; CCSDS TDM has keywords for yearly and diurnal aberration corrections and ODTK has an aberration-corrections setting. Twice or never is a 20″ error [CV: Veis 1960; GEODYN; Astronomical Almanac definition of astrometric place].
- **Diurnal aberration** (≤0.32″) cancels only under that receive-time/emit-time convention. A program that evaluates station and object at the same instant must apply it too. Orekit 12.0 and later has an AberrationModifier for RA/Dec measurements; check which velocity it uses against your light-time convention before relying on it, because a full observer velocity combined with a receive-time station double-counts the diurnal term [C]. Whatever applies the correction, test it on calibration satellites: residual means should be zero.
- **Light time.** Own reductions never apply it: the measurement model uses the observer at receive time and the object at emit time. A provider may have applied it, which is why the state is recorded (§12).
- **Parallactic refraction.** The object is closer than the stars and is refracted less, so its true direction is closer to the zenith than the star-relative position by ≈480″·(P/1013 hPa)·tan z / (range_km·cos z) (Murray 1983; Veis 1960 gives 435″). About 0.7″ at z = 45° and 1,000 km; under 0.05″ at GEO above 30° elevation and 0.1–0.2″ below 20° [CV].
- **Smaller terms that reach 0.1″:** chromatic refraction for unfiltered systems at low elevation (≈0.09″ per magnitude of BP−RP color difference × tan z); the aberration gradient across a wide field (evaluate the correction at the object's position, not the boresight); Gaia DR3 star positions left at epoch 2016.0.
- Mount-model (absolute) pointing needs the full correction chain and is far less accurate. Prefer star-relative.
- Declare frame and correction state on every record (§12). Legacy formats carry flags to read, not assume: B3 column 76 is the equinox indicator for optical observations (0 TEME of date, 1 mean of Jan 0, 2 J2000, 3 B1950) and may be blank.

**Timing (the dominant hidden error)**
- The time tag should be a GPS-disciplined hardware timestamp of the shutter or sensor trigger, not the operating-system clock at file write. In one documented case a ≈3.9″ RA offset at GEO was attributed to NTP-stamped frames ≈0.26 s late (Chote et al. 2025).
- Record exposure start, duration, and which instant the position refers to. An unknown reference (start or mid) is a bias of half the exposure, not noise. Rolling-shutter CMOS needs a per-row readout offset.
- Signature of a time bias: residuals along the apparent motion, proportional to angular rate (about twice as large on MEO navigation satellites as on GEO), and common to every object that sensor saw, including slot-mates in the same frames. A tagging or latency error is a constant step; a drifting clock wanders. At GEO a real east-west burn also appears along-track in RA, so direction alone does not discriminate (§13.2).
- Dec is the control channel: a clock error moves RA at the apparent rate and leaves Dec alone, so σ_RA > σ_Dec is timing jitter and a non-zero Dec median is a site, refraction, frame or truth-ephemeris error. The calibration search and a self-healing per-sensor bias policy are in §16.3.

**Calibration [CV]**
- Calibrate against precise ephemerides: GNSS (IGS and MGEX products), laser-ranged targets (ILRS: LAGEOS, Ajisai, Etalon) and operator ephemerides. For the GEO regime, MGEX covers BeiDou inclined-GEO and QZSS satellites, and BeiDou GEO from some analysis centers only, at decimeter-to-meter accuracy: ample against 180 m per arcsec. Name the product used.
- Estimate per-sensor RA, Dec and time biases plus noise each night; re-estimate after any hardware, focus or software change.
- Bias estimates arrive after the night's data. Promote observations with a provisional calibration state and re-version when the estimate lands.
- Site coordinates: ITRF with ellipsoidal height (§2).

**Failure modes:** annual aberration applied twice or never; J2000/TEME/apparent mixed; exposure start tagged as mid-exposure; streak endpoint order reversed; stale distortion model after refocus; centroid blended with a star or a neighboring satellite; saturated glint; GPS/UTC or leap-second slip; wrong site height.

## 5. Photometry and characterization

**Calibration [CV]**
- Calibrate differentially against in-field Gaia stars with a color term evaluated at solar color (BP−RP = 0.82), because satellites reflect sunlight. Chote et al. 2025 reach zero-point scatter of a few mmag and systematics below 0.05 mag this way; without a color term expect ≈0.1 mag RMS and field-dependent errors of a few tenths.
- Store instrumental and calibrated magnitudes, band, zero point ± σ, color term, airmass, aperture or PSF method, exposure, SNR, and saturation and blend flags. Trailed targets need streak apertures.

**Normalization**
- Range: m_norm = m − 5·log10(R/R_ref). Reference ranges differ between communities and data providers; store R_ref with the value and never compare across different R_ref.
- Geometry: store solar phase angle, and for GEO the signed solar equatorial phase angle and the Sun's declination (season). Compare light curves only at matched phase and season; otherwise the difference is geometry, not identity.

**What the light curve says**
- Three-axis-stabilized GEO: smooth phase curve with a solar-panel glint near zero equatorial phase. The glint peak offset reveals panel pointing offset (a 30° glint offset implies about a 15° panel offset). Glints are seasonal and strongest near the equinoxes; no glint out of season is not a change.
- Spinning or tumbling: periodic. Get the period with Lomb-Scargle or phase dispersion minimization and check the ×2 and ×0.5 aliases. The apparent period is synodic and shifts with geometry.
- Real fingerprint changes: docking (after MEV-2 docked with Intelsat 10-02 the main glint peak moved from 30° to about 5° phase, Chote et al. 2025), deployments, attitude-mode changes, loss of attitude control.
- High area-to-mass objects pair erratic photometry with large solar-radiation-pressure perturbations.

**Plausibility gate [CV].** For a diffuse sphere of radius r, Lambertian albedo ρ, range R and solar phase angle φ:
m = −26.74 − 2.5·log10[ (2ρr²)/(3πR²) · (sin φ + (π − φ)·cos φ) ].
Check value: r = 1 m, ρ = 0.175 (NASA's debris convention), R = 36,000 km, φ = 0 gives V ≈ 13.4. Use it as an order-of-magnitude check on brightness versus assumed size; specular glints exceed it by magnitudes.

**Quality guards for wide-field feeds [H]**
- Use the frame's zero-magnitude counts (the flux of a zero-magnitude star implied by the plate solution) as a sky-transparency monitor: magnitude = −2.5·log10(counts/ZMC) with a per-frame zero point, and a cached fallback keyed by binning and exposure. Drop frames whose ZMC falls below ~0.5× the night's median — clouds otherwise read as light-curve variation — then apply sliding-window outlier rejection.
- Record several per-frame limiting magnitudes (noise-limited, matched-filter, peak-pixel) and reject any detection fainter than every one of them by more than ~0.2 mag: near-threshold detections are mostly false. Floor photometric σ at ≈0.15 mag for uncalibrated feeds.
- Size gauge consistent with the plausibility gate at albedo ≈0.25: diameter ≈ 12.8 m·2^−(V−9)/1.5 at zero phase, good to about 2× (§2).

**Photometric noise and systematics**
- *Scintillation [CV]:* σ ≈ 0.09·D_cm^(−2/3)·X^1.75·e^(−h/8 km)/√(2t) mag (Young's relation: D aperture in cm, X airmass, h site altitude, t exposure in s) — ≈0.01 mag for 35 cm at 1 s, ≈0.03 at 0.1 s, ≈0.07 for 10 cm at 0.1 s: a floor for short exposures on small apertures that no calibration removes.
- *Vignetting and flat-field residuals [H]:* an in-field zero point assumes a flat response; 10–30% vignetting on fast optics becomes a 0.1–0.3 mag position-dependent error unless the flat is current, the zero point is fitted as a spatial model, or only stars near the target are used.
- *Undersampled PSFs [CV]:* at σ ≲ 0.5 px, sub-pixel position adds 0.01–0.05 mag of aperture scatter and ~0.1 px of centroid error; fit the PSF or use larger apertures, and do not bin into undersampling.
- *Non-linearity [H]:* a saturation flag at ~95% full well catches nothing below it; measure the linearity curve and flag photometry above ~70–80%.
- *Opposition surge [C]:* rough materials brighten by a few tenths of a magnitude within ~5° of zero phase; near local midnight that is material, not an event.

**Magnitude corrections and illumination terms**
- *Correction ladder [CV]*, applied in this order and recorded with its version: instrumental counts → per-frame zero point from in-field stars (extinction, airmass and uniform cloud cancel; patchy cloud appears as zero-point scatter) → bandpass or colour transform evaluated at solar colour → range normalization to a stated R_ref (36,000 km and 40,000 km are both in use, so the value is meaningless without it) → phase treatment: compare at matched phase and season (preferred for fingerprinting), or reduce to a reference phase with a *named* phase function carried as a flag, because the model is part of the number → trailing-loss correction for streaked targets. Values that stopped at different rungs are not comparable.
- *Earthshine [physics].* Earth subtends 0.072 sr from GEO. At best — the object at local noon, Earth fully lit — Earth-reflected sunlight on the nadir face is ≈0.5% of direct solar irradiance (≈ −5.8 mag), and it vanishes at the object's local midnight, exactly when a ground observer sees it at minimum phase. For a diffuse body it exceeds 0.1 mag only beyond ≈140° phase or on surfaces that only Earth lights; otherwise it sits under the ≈0.05–0.1 mag calibration noise and cannot explain a brightening near local midnight. From 550 km the Earth fills ≈2.7 sr (projected) and earthshine on the nadir side reaches ≈25% of sunlight (≈ −1.5 mag): include it in LEO brightness models and twilight visibility predictions. Earth's thermal emission (≈240 W/m² at the top of the atmosphere) matters only to infrared sensors; the Earth-albedo and infrared radiation pressure it implies are ≈0.5% and 0.4% of solar radiation pressure at GEO, negligible for orbit determination.

**Scheduled signature changes [CV].** Some buses perform a 180° yaw flip around each equinox for radiator management; yaw-steering navigation satellites make noon and midnight yaw turns timed by the Sun's elevation above the orbit plane; arrays are feathered or off-pointed for power or thermal management. Each changes the phase curve on a calendar — check it before calling a change. Lunar-shadow transits (a solar eclipse seen from the object) dim a GEO satellite partially for up to an hour and totally for minutes, a few times a year across the belt; Earth-penumbra passes dim it for ≈2 min at each eclipse edge. Both are coincidences to rule out (§9).

**Reporting a signature change [H].** Say *where* (time within the observing window, or the phase-angle region), the *direction and feature* (brighter/dimmer, spike, peak, glint, flattened peaks — never "decrease in magnitude", which reads both ways), the *size* in magnitudes, the *comparison basis* (previous night, a dated baseline, the same sensor's last observation), the *sensor count* and the *hemisphere or site geometry*. Before attributing a change to the object, check the coincidence list: eclipse or Moon, a conjunction or longitude crossing with a neighbour (possible cross-tag, §8), a change in sampling because the drift rate changed, and the edges of the observing window, where phase angle is high and the phase curve steep. A change recurring at the same clock time on unrelated objects is a sensor hand-off or geometry, not behaviour. A signature that changes every night is a variability *state*: re-baseline it instead of issuing daily change calls. The confirmation rule is in §13.4.

**Machine learning on light curves** (classification, embeddings for re-identification) is useful for screening and is limited by label scarcity and the simulation-to-real gap [C]. Corroborate identity calls with an orbit or RF check.
