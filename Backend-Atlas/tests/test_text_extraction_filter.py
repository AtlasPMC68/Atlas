from app.utils.text_extraction import process_candidate_text, should_ignore


def test_should_ignore_numeric_and_scale_annotations():
    assert should_ignore("1783")
    assert should_ignore("600 Km")
    assert should_ignore("600km")
    assert should_ignore("Échelle 1:50000")
    assert should_ignore("Miles")


def test_process_candidate_text_preserves_numbers_in_place_names():
    quad = [[0, 0], [10, 0], [10, 10], [0, 10]]

    assert process_candidate_text("Route 600", quad)["text"] == "Route 600"
    assert process_candidate_text("Québec 1783", quad)["text"] == "Québec 1783"
    assert process_candidate_text("600 Km", quad) is None
