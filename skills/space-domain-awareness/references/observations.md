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

**Machine learning on light curves** (classification, embeddings for re-identification) is useful for screening and is limited by label scarcity and the simulation-to-real gap [C]. Corroborate identity calls with an orbit or RF check.
