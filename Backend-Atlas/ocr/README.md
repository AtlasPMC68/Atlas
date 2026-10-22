# OCR prototyping

Benchmark harness for the backend's OCR (`../app/utils/ocr`): runs its pipeline on
every test image, saves overlays and scores the result against the extraction
tests' expected words. The backend code is mounted read-only, so this always
measures what production runs.

## Run it

From the repo root:

```bash
# all images under Backend-Atlas/tests/assets
docker compose -f Backend-Atlas/ocr/docker-compose.yml run --rm ocr-proto

# only images whose path contains one of the filters
docker compose -f Backend-Atlas/ocr/docker-compose.yml run --rm ocr-proto python3 -u run.py quebec 52a1aedc
```

Score the latest runs against the extraction tests' expected words
(`tests/utils/expected_text_results.py`). Standard library only, runs on the host:

```bash
python3 Backend-Atlas/ocr/compare.py [run_dir ...]   # default: latest run of each kind
```

The image is the backend's own (`../Dockerfile`). Both folders are mounted, so
code edits don't need a rebuild.

## Output

`outputs/<timestamp>-ocr/` (gitignored, on the host):

```
summary.txt                      one line per image + run totals (avg / median / min / max)
timeline.csv                     start/finish timestamps per image, time since previous image, stage timings
<asset path>/overlay.png         original image, numbered boxes + reading
<asset path>/comparison.txt      [n] 'text'
<asset path>/result.json         every box with its text and reader score
```

The numbers in `comparison.txt` match the numbers on `overlay.png`.

## How it works

See `../app/utils/ocr/inference.py`:

1. Small maps are upscaled to 1000-2000 px, then `PP-OCRv5_server_det` finds the
   boxes on the whole image. It only uses convolutions, so no tiling: it takes any
   size up to 4000 px on the long side.
2. Each box is cut out of the original image (15% margin), straightened, and read
   as-is / CLAHE / Otsu binarized (both 90° turns for tall boxes) in one batch by
   `latin_PP-OCRv5_mobile_rec`. The most confident reading wins.

## Results (9 maps with expected words)

| Detector | Reader | Boxes found vs expected | Expected words found | Avg word distance | s / map |
| --- | --- | --- | --- | --- | --- |
| PP-OCRv5 server det | PP-OCRv5 latin | 174.7% | 97.2% | 0.31 | 3.1 |

"Boxes found" is above 100% because the expected counts were recorded from an
earlier OCR that grouped words differently, not hand-counted.

## Notes

- The reader fixes most misreadings (`Povimitua -> Puvirnituq`, `Gaspa -> Gaspé`).
- Remaining misses: letter-level misreads (`Mongreal`, `Larochefte`), stray
  characters (`Bostond`), and multi-word labels split in several boxes
  (`Orléans` without `La Nouvelle-`).
- Paddle sometimes fires big boxes on empty land (`SE`, `SUS` on `Nouvelle-France1750`).
- PALETTE (map text spotter) is GPU-only (CUDA 11.3, gated, custom commercial
  licence). DBNet++ needs the unmaintained MMOCR stack.

## Next ideas

- Drop boxes with a low reader score (should remove the empty-land boxes).
- Hand-label a few maps to get an actual error rate.
