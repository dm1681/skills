# Evidence

Every gate run writes one folder; nothing is kept only in a transcript.

```
<evidence_root>/<character>/<run>/<stage>/
  summary.json                 verdict, every gate, notes, escalation advice
  structural_checklist.md      tick, then `gate.py finalize <this folder>`
  gates/
    silhouette_front.json      IoU, boundary, framing error, proportions
    face_tier1.json            scores, face_px, noise_floor
    face_tier4_head_front.json one per head reference
    regression.json            per-shot LPIPS, hotspots (with --prev)
  overlays/
    ref_mask_front.png         the reference matte the solve used
    silhouette_front.png       white both / red reference only / cyan render only
    regression_r_head_front.png  render | heatmap, one per shot (with --prev)
  renders/
    r_fullbody_front.png       solved onto the reference box (+ @2 / @-2 jitter)
    r_head_front.png ...       head close-ups (+ jitter for each head reference)
    r_fullbody.json, r_head.json   camera, solve residual, normalisation, look
    blender_*.log
```

## summary.json (example)

```json
{
  "character": "ayla",
  "stage": "cleanup",
  "run": "attempt-3",
  "verdict": "LOOKALIKE",
  "gates": {
    "silhouette_front": {"verdict": "REPORT",
      "metrics": {"iou_aligned": "REPORT", "boundary_mean_pct_h": "REPORT"},
      "evidence": ".../gates/silhouette_front.json"},
    "face_tier1": {"verdict": "LOOKALIKE", "tier": 1,
      "metrics": {"identity_cosine": "REPORT", "dreamsim_face": "LOOKALIKE"},
      "evidence": ".../gates/face_tier1.json"},
    "dreamsim_full": {"verdict": "REPORT", "value": 0.118,
      "note": "uncalibrated: report only, never gates"},
    "regression": {"verdict": "PASS",
      "likeness_drops": {"face_tier1.dreamsim_face":
        {"worse_by": 0.008, "allowed": 0.0131, "verdict": "PASS"}}},
    "structural": {"verdict": "MANUAL", "evidence": ".../structural_checklist.md"}
  },
  "notes": [],
  "next": ["face LOOKALIKE: this is geometry work (face shape), not texture work -- texture passes do not move identity",
           "REPORT gates are uncalibrated: they are evidence, not pass/fail"]
}
```

## gates/face_tier1.json (example)

```json
{
  "tier": 1,
  "dreamsim_full": 0.118,
  "face_px": 105,
  "eye_dist_px": {"ref": 37.5, "render": 30.7},
  "dreamsim_face": 0.144,
  "identity_cosine": 0.543,
  "noise_floor": {"identity_cosine": 0.022, "dreamsim_face": 0.005},
  "warnings": []
}
```

Read a face score only with its tier and against that tier's calibration: here
`dreamsim_face` 0.144 sits between a calibrated `pass_at` of 0.130 and `fail_at`
of 0.152, hence `LOOKALIKE`.

When handing work back or asking the user for a decision, link the stage folder
and name the overlay or heatmap that shows the point.
