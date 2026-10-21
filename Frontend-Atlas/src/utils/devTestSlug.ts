/**
 * Mirror of the backend's `slugify_test_case` (Backend-Atlas/app/utils/dev_test.py).
 *
 * A dev-test case is stored on disk under its slug, and the API slugifies
 * whatever id it is given. Static artifacts (`zones.geojson`, `errors.geojson`)
 * are served straight off that directory, so a page reached with the raw case
 * name -- "test 5 sift points" rather than "test-5-sift-points" -- loads its
 * report through the API but 404s on its zones, and shows an empty map with no
 * error. Slugify on the client too, so both halves ask for the same thing.
 *
 * Kept deliberately identical to the backend, accents included: it strips them
 * rather than transliterating, so "québec" is "qubec" on both sides. Changing
 * that means changing both at once, plus the directories already on disk.
 */
export function slugifyTestCase(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 80);
}
