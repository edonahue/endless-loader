# Design Notes

Endless Loader is a utility for a small pedal workflow, so the UI should feel like a control surface rather than a generic file browser.

## Product Intent

- Phone-first control while the Raspberry Pi runs near the pedal.
- Desktop-friendly testing on Ubuntu-family machines.
- Clear USB readiness before a patch write.
- Fast recovery when returning to the project after time away.

## Web UI Model

The main screen is a pedal console:

- The selected patch is presented as the primary pedal card.
- Knobs are display controls for metadata and intent, not live parameter editors.
- The USB status panel explains whether loading is safe.
- The floating beacon gives a persistent ready, pending, or error signal.
- Rig context keeps setup facts visible without adding a separate diagnostics page.

## LCD Model

The optional 1602 LCD mirrors the loaded patch:

- Line 1 shows the patch name, truncated to 16 characters.
- Line 2 shows compact knob labels, truncated to fit.
- Error states show `Load Error` plus a shortened message.

## Future Hardware Controls

Physical controls should build on the current web flow:

- next patch
- previous patch
- load selected patch

The hardware path should reuse the same catalog, deployment, state, and LCD services rather than creating a separate patch-loading workflow.
