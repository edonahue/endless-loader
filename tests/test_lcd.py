from endless_loader.models import KnobMetadata, PatchRecord
from endless_loader.services.lcd import build_knob_line, build_patch_lines


def test_build_knob_line_uses_fixed_four_character_labels() -> None:
    knobs = (
        KnobMetadata("left", "Sustain", "desc", "Sust"),
        KnobMetadata("mid", "Tone", "desc", "Tone"),
        KnobMetadata("right", "Blend", "desc", "Blen"),
    )

    assert build_knob_line(knobs) == "Sust/Tone/Blen  "


def test_build_patch_lines_dim_unused_knobs() -> None:
    patch = PatchRecord(
        rel_path="effects/builds/phase_90.endl",
        abs_path=None,  # type: ignore[arg-type]
        filename="phase_90.endl",
        display_name="Phase 90",
        source_family="custom_sdk",
        knobs=(
            KnobMetadata("left", "Unused", "desc", "----", active=False),
            KnobMetadata("mid", "Speed", "desc", "Spee"),
            KnobMetadata("right", "Unused", "desc", "----", active=False),
        ),
    )

    line_1, line_2 = build_patch_lines(patch)
    assert line_1 == "Phase 90        "
    assert line_2 == "----/Spee/----  "

