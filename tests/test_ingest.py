from promo_tool.ingest import parse_script, parse_structured_script, chunk_lines


def test_structured_parsing(lines):
    """Sample script should parse into structured lines with element types."""
    assert len(lines) == 14
    assert {l.episode for l in lines} == {1}
    # First line is a CAMERA element
    assert lines[0].element_type == "camera"
    assert lines[0].text.startswith("CAMERA:")
    assert lines[0].number == 1
    # Line 4 is dialogue
    assert lines[3].element_type == "dialogue"
    assert lines[3].speaker == "ELENA"
    assert "Confused" in (lines[3].tone or "")


def test_timestamps_from_script(lines):
    """Structured scripts have exact timestamps on every element."""
    assert lines[0].start == 0.0
    assert lines[0].end == 3.5
    # Line 7 (VICTORIA dialogue): Start: (00:09.50) | End: (00:11.50)
    assert lines[6].start == 9.5
    assert lines[6].end == 11.5
    # Last line (Cut to black): Start: (00:24.00) | End: (00:25.00)
    assert lines[-1].start == 24.0
    assert lines[-1].end == 25.0


def test_element_types(lines):
    """Check that element types are correctly classified."""
    types = [l.element_type for l in lines]
    assert types.count("camera") == 5
    assert types.count("action") == 3
    assert types.count("dialogue") == 5
    assert types.count("sound_fx") == 1


def test_scene_numbers(lines):
    """All lines should be in scene 1."""
    assert all(l.scene == 1 for l in lines)


def test_legacy_fallback():
    """Legacy format (no --- SCRIPT START ---) should still parse."""
    text = "Episode 1\n" + "\n".join(f"SPEAKER: line {i}" for i in range(5))
    lines = parse_script(text)
    assert len(lines) == 5
    assert lines[0].episode == 1


def test_chunks_cover_everything_with_overlap():
    text = """EPISODE NUMBER: Episode 1
--- SCRIPT START ---
SCENE 01
Scene heading: INT. ROOM – DAY
Scene start: 00:00.00
Scene end: 00:10.00

Actions and dialogue:

""" + "\n".join(f"""**CAMERA:**
Start: (00:0{i}.00) | End: (00:0{i}.50)
Shot number {i} showing something happening in the room.
""" for i in range(10))
    text += "\n--- SCRIPT END ---"
    lines = parse_structured_script(text)
    chunks = chunk_lines(lines, max_words=30, overlap_lines=2)
    seen = {l.key for c in chunks for l in c.lines}
    assert seen == {l.key for l in lines}
    assert len(chunks) > 1
