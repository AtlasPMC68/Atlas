from app.utils.text_extraction import _filter_detections, _to_blocks, clean_candidate_text, should_ignore


def test_should_ignore_numeric_and_scale_annotations():
    assert should_ignore("1783")
    assert should_ignore("600 Km")
    assert should_ignore("600km")
    assert should_ignore("Échelle 1:50000")
    assert should_ignore("Miles")


def test_clean_candidate_text_keeps_numbers_but_strips_years():
    assert clean_candidate_text("Route 600") == "Route 600"
    assert clean_candidate_text("Québec 1783") == "Québec"
    assert clean_candidate_text("Boston (1630)") == "Boston"
    assert clean_candidate_text("600 Km") is None


def test_filtered_detections_keep_their_ocr_score():
    quad = [[0, 0], [10, 0], [10, 10], [0, 10]]
    detections = [{"text": "Québec 1783", "score": 0.42, "quad": quad}, {"text": "600 Km", "score": 0.9, "quad": quad}]

    assert _to_blocks(_filter_detections(detections)) == [{"text": "Québec", "bbox": quad, "prob": 0.42}]
