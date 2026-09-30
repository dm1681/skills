# Lookup guide and landscape snapshot

Part of the `space-domain-awareness` skill. Section numbers (§) match the map in `SKILL.md`.

## 14. Lookup guide

**Look further when**
- the item is marked [C] or is time-sensitive (all of §15, and the status of any program, company or standard version);
- an [H] number is about to go into code, a requirement or a decision: find a published basis, or derive and tune it on the user's data;
- field-level detail of a format or schema is needed;
- a formula or constant is going into code: confirm it against a primary reference and test it on a known case;
- the question is outside this file, or the method is newer than September 2026;
- the user's data contradicts a number here: investigate both before trusting either.

**How to look**
- Prefer primary sources (standards bodies, agency handbooks, peer-reviewed papers, provider documentation) to summaries. Cite what was used and record the version and date of any standard.
- Keep the user's proprietary or controlled data out of queries (rule 8).
- With no search tool available, say so and mark the value unverified.
- Label what is found [PS], [CV], [H] or [C] like everything else.

**Where to look**
| Need | Source |
|---|---|
| Message formats and fields | CCSDS Blue Books (ccsds.org): ODM 502.0-B-3, TDM 503.0-B-2, CDM 508.0-B-1, ADM 504.0-B-2, RDM 508.1-B-1, NDM/XML 505.0-B-3; SANA registry for keyword values |
| Government data schemas | Unified Data Library documentation (account needed) and the public `udl-sdk` package (PyPI; Bluestaq/udl-python-sdk); Space-Track documentation (space-track.org/documentation) |
| GP data, SupGP, catalog-number transition | CelesTrak (celestrak.org), including its GP data formats page |
| SGP4 reference implementation | Vallado et al., "Revisiting Spacetrack Report #3" and code at CelesTrak |
| Conjunction thresholds and practice | NASA NPR 8079.1; NASA Conjunction Assessment Best Practices Handbook (Rev 2, 2026, two volumes; thresholds in Vol. 2 App. F); 19 SDS Spaceflight Safety Handbook (Space-Track); TraCSS page, FAQ and TraCSS-Spec documents (space.commerce.gov) |
| Frames, time, Earth orientation | IERS Conventions and bulletins (iers.org); SOFA/ERFA; Orekit and astropy documentation |
| Orbit determination and estimation | Tapley, Schutz and Born, *Statistical Orbit Determination*; Montenbruck and Gill, *Satellite Orbits*; Vallado, *Fundamentals of Astrodynamics and Applications*; Milani and Gronchi, *Theory of Orbit Determination* |
| Tracking and data association | Bar-Shalom et al.; Blackman and Popoli; Mahler for random finite sets |
| New methods: photometry, PoL, covariance realism, tasking | AMOS proceedings (amostech.com); arXiv; AAS/AIAA astrodynamics conferences; ESA Space Debris Conference proceedings; *Journal of Guidance, Control, and Dynamics*; *Journal of the Astronautical Sciences*; *Acta Astronautica*; *Advances in Space Research* |
| Space weather indices and forecasts | NOAA SWPC; CelesTrak space-weather files; GFZ Potsdam for Kp |
| Atmosphere model uncertainty | ECSS-E-ST-10-04C Annex G; the model papers |
| Calibration truth | IGS and MGEX orbit products (igs.org); ILRS (ilrs.gsfc.nasa.gov); Gaia archive (DR3 is current until DR4, scheduled for 2 December 2026) |
| Object metadata and history | Space-Track SATCAT and GP history; ESA DISCOS; Jonathan McDowell's GCAT (planet4589.org/space/gcat) |
| Benchmark data | MIT ARCLab SPLID (github.com/ARCLab-MIT/splid-devkit); ESA Kelvins collision-avoidance challenge (also on Zenodo); MMT-9 satellite photometry archive (hosted in Russia: check organizational policy first) |
| Disposal and debris guidelines | IADC Space Debris Mitigation Guidelines (IADC-02-01) |
| Threat and behavior context | Secure World Foundation *Global Counterspace Capabilities*; CSIS *Space Threat Assessment* and its unusual-behavior-in-GEO data (annual) |
| Doctrine and analytic standards | USSF Space Doctrine Publication 3-100; Intelligence Community Directive 203 |
| Status of any program, company or product | web search, every time |

**Ask the user** for pipeline schemas and conventions, sensor specifications and calibration history, provider licenses and data rights, thresholds their organization has adopted, and classification or export-control guidance.

**Stop** when the answer would need non-public or classified information, and say so.

**Papers cited in this file:** Chote et al. 2025, PHANTOM ECHOES 2 light curves (arXiv:2506.01549) · Gazak et al., AMOS 2025 · Schildknecht et al. 2005, 4th European Conference on Space Debris · Skuljan, AMOS 2021 · Decoto and Loerch, AMOS 2015 · Flohrer, Krag and Klinkrad, AMOS 2008 · Levit and Marshall 2011 (arXiv:1002.2277) · Parker and Linares 2024 (arXiv:2406.08617) · Siew et al., AMOS 2023 (SPLID) · Holzinger, Scheeres and Alfriend 2012, JGCD 35(4) · Payne et al., AMOS 2022 (SGP4-XP) · Vallado, AAS 01-429 · Vallado et al. 2006, AIAA 2006-6753 · Veis 1960, Smithsonian Contributions to Astrophysics 3(9).

## 15. Landscape snapshot

As of September 2026. Every line goes stale; verify by search before relying on it.

- **US government:** Space Force SDA operations sit in Mission Delta 2. The 18th Space Defense Squadron maintains the catalog and the 19th runs the orbital-safety and conjunction-assessment crew behind Space-Track conjunction messages. The National Space Defense Center covers protect-and-defend. The Joint Commercial Operations cell works from commercial data. The Unified Data Library is the Space Force data store and its schemas are the de facto baseline. The SDA TAP Lab runs commercial technology cohorts. Doctrine is in SDP 3-100.
- **Civil:** the Office of Space Commerce's TraCSS is a free, pilot-phase service running in parallel with Space-Track. There is no production declaration and no hand-over date, and its funding and a possible fee model are unresolved. NASA CARA covers NASA missions. EU SST serves European operators.
- **Commercial, by modality:** optical networks (ExoAnalytic, which Anduril agreed to acquire in March 2026, closing not publicly confirmed; Slingshot), radar (LeoLabs), passive RF (Kratos, Safran), space-based sensing (NorthStar, Digantara, Vyoma, HEO; SpaceX Stargaze using Starlink star trackers, performance unverified), analytics and safety services (COMSPOC, Kayhan, Slingshot, Privateer).
- **Threat context:** the annual Secure World Foundation and CSIS reports are the public baseline for counterspace capabilities and unusual on-orbit behavior.
