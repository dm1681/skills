# Data standards, sources and pipeline design

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 11. Data standards and sources

| Format | Holds | Watch for |
|---|---|---|
| TLE / 3LE | SGP4 mean elements | 5-character ID field (§8), 2-digit year, no covariance, no frame or time fields (TEME and UTC implied) |
| CCSDS OMM (ODM 502.0-B-3) | mean elements | integer catalog ID, ISO epoch, MEAN_ELEMENT_THEORY, optional covariance |
| CCSDS OPM / OEM | state / ephemeris | REF_FRAME, CENTER_NAME, TIME_SYSTEM, interpolation, covariance |
| CCSDS OCM (in ODM v3) | trajectory, covariance, maneuvers, physical properties, orbit-determination metadata | the richest container; optional blocks vary by producer |
| CCSDS TDM (503.0-B-2) | tracking data: angles, range, Doppler | which corrections were already applied |
| CCSDS CDM (508.0-B-1) | conjunction data | covariance frame (RTN), Pc method; TraCSS publishes its own CDM specification on top of it |
| CCSDS ADM (504.0-B-2), RDM (508.1-B-1) | attitude; re-entry | frame and quaternion conventions |
| VCM / SP vectors | USSF special-perturbations state and covariance | covariance realism |
| B3 | legacy fixed-width observations | column 76 equinox flag (§4); implied decimals |
| UDL schemas | observations (optical, radar, RF), element sets, state vectors, conjunctions, maneuvers | de facto USSF schema baseline (below) |
| FITS | imagery | DATE-OBS convention, EXPTIME, WCS, filter, gain, track mode |

- **UDL optical observations:** field names are public in the `udl-sdk` package. As read in 2026, only classification marking, data mode, observation time and source are required and every measurement field is optional; a null reference frame means J2000; data mode can be REAL, TEST, SIMULATED or EXERCISE; what the time tag marks, which corrections were applied and whether the bias fields are already removed are left to each provider's data card; angular uncertainties are in degrees with no statement of the cos δ convention; sensor altitude is in km with no height datum. Verify against the live schema.
- Allowed keyword values for CCSDS messages are in the SANA registry for ODM, TDM, ADM and RDM; the CDM enumerates its frames itself.
- Source locations are in §14.

## 12. Pipeline and data lake design

**Layers.** Each is derived from the one before and reproducible from it.
1. *Raw:* immutable payloads (FITS, JSON/XML, TDM, B3, OMM, CDM) with content hash, source, ingestion time, data rights and markings.
2. *Detections:* pixel positions, SNR, PSF or streak parameters, saturation and blend flags.
3. *Calibrated observations:* angles with declared frame and correction state, time with scale and uncertainty, calibrated photometry, the bias corrections applied and their version.
4. *Associations and tracks:* probabilistic links, tracklets, uncorrelated-track clusters.
5. *Orbit solutions:* versioned fits with covariance, residual summaries and realism metrics.
6. *Behavior features:* maneuver candidates, drift and deadband features, cadence statistics, photometric features, embeddings.
7. *Assessments:* judgments with confidence, hypotheses considered, sourcing and links to evidence.

**Two entry paths.** Own-sensor data flows raw → detections → calibrated observations. Provider-reduced observations (UDL, commercial feeds) have no pixels: they enter at calibrated observations under their own gates. They stay unusable for orbit fits until the provider's conventions are known (what the time tag marks, which corrections were applied, whether biases are removed, on-sky or coordinate sigma) and the sensor has been checked against calibration satellites. Store positions as delivered with their correction states and let the measurement model apply what each state requires; never convert in place. Where a provider gives no uncertainty, assign one from your own residual statistics for that sensor and record its source. Your own observations can come back through a shared library with reformatted values; match the echo on sensor, time and angles within tolerance and link it instead of counting it twice.

**Block or flag.** Block a record only when it cannot be trusted as a measurement at all: undeclared conventions or lineage, failed time integrity or geometry sanity, a failed plate solution or fit, not real data (test, simulated, exercise), or no governance tags. Blocked records go to a quarantine table with reason codes and stay queryable. Duplicates are linked, not added. Everything else is promoted with flags and per-use usability fields (astrometry usable, photometry usable), because rejected observations are often the first evidence of a maneuver.

**Metadata every observation needs**
- *Identity:* stable observation ID, version ID, sensor ID, provider, delivery route, pointer to and hash of the raw payload, provider-asserted object ID.
- *Time:* raw timestamp, time scale, the instant it marks (exposure start, mid or end), exposure duration, clock source (GPS-PPS, PTP, NTP), time uncertainty, time-bias correction applied and its version.
- *Geometry:* sensor position (ITRF, ellipsoidal height) or sensor state for space-based, measurement frame, track mode, astrometry method (star-relative or mount-model), and correction states as enumerations: annual aberration (astrometric, applied, unknown), light time (not applied, applied, unknown), refraction (removed, present, unknown).
- *Measurement:* values with units, 1σ uncertainties and their convention (§4), bias corrections and calibration version.
- *Photometry:* the fields in §5. Range- and phase-normalized values depend on an orbit, so they live downstream, versioned with it.
- *Reference data versions:* star catalog, Earth orientation parameters, leap-second table.
- *Times and versions:* observation time, ingestion time, processing time, superseded time.
- *Governance:* data rights and license, export-control and classification markings, releasability.

**Design rules**
- **Three keys, not one.** A stable observation ID (from the raw payload hash and detection index, or a hash of the provider's record), a version ID (code, calibration and reference-data versions) and a cross-route dedup key (sensor, raw time tag, as-delivered angles). Recalibration changes time and angles, so neither can be the identity.
- **Bitemporal and versioned.** Reprocessing writes a new version and marks the old one superseded; nothing is overwritten. Late data trigger a re-fit of the affected window. Table-format time travel is not history: snapshot expiry deletes it.
- **Point-in-time features.** Compute training features as they were known at the time, not from later reprocessed orbits, or labels leak into the model and offline scores will not hold in operation.
- **Identity as a link table** (§8), never a hard foreign key on catalog number.
- **Units and frames as schema,** not convention: one canonical unit per quantity, frame and time scale as required enumerated columns.
- **Storage.** Apache Iceberg or Delta Lake for ACID writes and schema evolution. Partition observation tables by observation day and sort by sensor and time (object and regime are unknown before association). Partition orbit and feature tables by day and regime, sorted by object and time. Never partition on object or sensor ID alone. A HEALPix index serves sky-region queries.
- **Governance tags travel with derived data,** and a source's license terms apply to products built from it.

**Gates by layer boundary.** Thresholds for star counts, SNR floors and elevation limits are sensor-specific: derive them from each sensor's own history, not fixed constants [H].

| Boundary | Gate | Test | On failure |
|---|---|---|---|
| Into calibrated observations | Lineage and declared conventions | raw payload resolves; frame, time scale, units and site position each come from an explicit source | block |
| | Time integrity | exposures monotonic and non-overlapping; tag inside the exposure window and not after ingestion | block |
| | Geometry sanity | target above the horizon and lighting consistent with the sensor (Sun below the horizon for night-only sensors; Earth-limb and Sun exclusion for space-based) | block: it signals a time, site or frame error |
| | Plate solution | star residual RMS within the sensor's rolling norm; enough stars, spread across the field, target inside them | block the frame |
| | Measurement validity | fit converged; values finite; σ positive | block |
| | Photometric validity | unsaturated, unblended, SNR and zero-point scatter acceptable | flag photometry only |
| | Duplicates | exact and near-duplicate across routes | link, do not add |
| Sensor-night, after calibration passes | Truth cross-check | calibration-satellite residuals against precise ephemerides; no motion-aligned pattern | flag the sensor-night; estimate bias; re-version |
| At association | Residual against the object's orbit | inside the gate (§8) | flag and de-weight; open §13.2; never block |
| | Photometric plausibility | magnitude consistent with size, range and phase (§5) | flag possible mis-tag |
| At orbit solution | Orbit plausibility | perigee above ~100 km altitude; energy and angular momentum fit the regime | reject the solution |
| | Drag and radiation-pressure terms | physical range (§2) | flag |
| | Covariance | positive definite; realism statistics in bounds (§6) | inflate or flag |
| At features | ΔV plausibility | implied ΔV against class and history | open a maneuver hypothesis (§13.2) |
| Every batch | Conservation and drift | rows in = promoted + quarantined, each with a reason; per-sensor yield and mean residual inside control limits | hold the batch |
