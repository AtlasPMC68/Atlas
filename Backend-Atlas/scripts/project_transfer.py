"""Export a project (and everything attached to it) to one JSON file, and
import such a file into another Atlas instance (typically production).

Run through the wrapper at the repository root, which starts a one-off
backend container with the right volumes:

    npm run export                      # interactive project list
    npm run import -- exports/foo.json  # on the server

or directly:  ./scripts/project-transfer.sh export | import <file>

What is transferred:
  * projects      the row, including its image and label styles
  * maps          every map of the project, including georef_inputs
  * features      every feature of the project, including its image
  * reference images of the maps (files under MEDIA_ROOT), embedded in base64

What is not:
  * map_imports   imports still in progress: their state is tied to the local
                  Celery tasks. Their map is exported without features.
  * the owner     on import, the project always belongs to --owner ("demo").

Rows keep their UUIDs, so importing the same project twice is detected and
refused. Rows are serialised with to_jsonb() and restored with
jsonb_populate_record(), so columns added by future migrations are carried
over without changing this script.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

FORMAT = "atlas-project"
FORMAT_VERSION = 1
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/app/media"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(message: str) -> None:
    print(f"\n[ERREUR] {message}", file=sys.stderr)
    sys.exit(1)


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        die("DATABASE_URL n'est pas défini.")
    # SQLAlchemy URL (postgresql+psycopg://) -> libpq URL (postgresql://)
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    try:
        return psycopg.connect(url, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        die(f"Connexion à la base de données impossible ({exc}). La stack est-elle démarrée ?")


def applied_migrations(conn: psycopg.Connection) -> list[str]:
    exists = conn.execute("SELECT to_regclass('schema_migrations') AS t").fetchone()["t"]
    if not exists:
        return []
    rows = conn.execute("SELECT filename FROM schema_migrations ORDER BY filename").fetchall()
    return [r["filename"] for r in rows]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:50] or "projet"


def ask(prompt: str) -> str:
    if not sys.stdin.isatty():
        die("Pas de terminal interactif : passe les options en argument (voir --help).")
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        die("Annulé.")
    return ""


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} To"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def choose_project(conn: psycopg.Connection) -> dict:
    projects = conn.execute(
        """
        SELECT p.id, p.title, u.username,
               p.updated_at,
               (SELECT count(*) FROM maps m WHERE m.project_id = p.id)     AS maps,
               (SELECT count(*) FROM features f WHERE f.project_id = p.id) AS features
        FROM projects p
        LEFT JOIN users u ON u.id = p.user_id
        ORDER BY p.updated_at DESC NULLS LAST
        """
    ).fetchall()
    if not projects:
        die("Aucun projet dans la base de données.")

    print("\nProjets disponibles :\n")
    width = len(str(len(projects)))
    for i, p in enumerate(projects, 1):
        updated = p["updated_at"].strftime("%Y-%m-%d") if p["updated_at"] else "?"
        print(
            f"  {i:>{width}}. {p['title']}  "
            f"[{p['username'] or '?'}] — {p['maps']} carte(s), "
            f"{p['features']} élément(s), modifié le {updated}"
        )

    while True:
        answer = ask(f"\nNuméro du projet à exporter (1-{len(projects)}, q pour quitter) : ")
        if answer.lower() in ("q", "quit", ""):
            die("Annulé.")
        if answer.isdigit() and 1 <= int(answer) <= len(projects):
            return projects[int(answer) - 1]
        print("Choix invalide.")


def export_project(args: argparse.Namespace) -> None:
    with connect() as conn:
        if args.project_id:
            project_ref = conn.execute(
                "SELECT id, title FROM projects WHERE id = %s", (args.project_id,)
            ).fetchone()
            if not project_ref:
                die(f"Projet {args.project_id} introuvable.")
        else:
            project_ref = choose_project(conn)

        pid = project_ref["id"]

        project = conn.execute(
            """
            SELECT to_jsonb(p) AS row, u.username AS owner
            FROM projects p LEFT JOIN users u ON u.id = p.user_id
            WHERE p.id = %s
            """,
            (pid,),
        ).fetchone()
        maps = [
            r["row"]
            for r in conn.execute(
                "SELECT to_jsonb(m) AS row FROM maps m WHERE m.project_id = %s ORDER BY m.created_at",
                (pid,),
            )
        ]
        features = [
            r["row"]
            for r in conn.execute(
                "SELECT to_jsonb(f) AS row FROM features f WHERE f.project_id = %s ORDER BY f.created_at",
                (pid,),
            )
        ]
        pending_imports = conn.execute(
            """
            SELECT m.title FROM map_imports mi JOIN maps m ON m.id = mi.map_id
            WHERE m.project_id = %s
            """,
            (pid,),
        ).fetchall()
        migrations = applied_migrations(conn)

    project_row = project["row"]
    project_row["user_id"] = None  # replaced by the target owner on import

    # Reference images live on disk, not in the database
    reference_images = {}
    for m in maps:
        rel = m.get("reference_image_path")
        if not rel:
            continue
        path = (MEDIA_ROOT / rel).resolve()
        if MEDIA_ROOT.resolve() not in path.parents or not path.is_file():
            print(f"[AVERTISSEMENT] Image de référence introuvable pour la carte « {m['title']} » ({rel}), ignorée.")
            m["reference_image_path"] = None
            m["reference_image_content_type"] = None
            continue
        reference_images[m["id"]] = {
            "filename": path.name,
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    payload = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_owner": project["owner"],
        "schema_migrations": migrations,
        "project": project_row,
        "maps": maps,
        "features": features,
        "reference_images": reference_images,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_file = out_dir / f"{slugify(project_row['title'])}_{stamp}.json"
    with out_file.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)

    print(f"\n[OK] Projet « {project_row['title']} » exporté.")
    print(f"     {len(maps)} carte(s), {len(features)} élément(s), {len(reference_images)} image(s) de référence")
    print(f"     Fichier : exports/{out_file.name} ({human_size(out_file.stat().st_size)})")
    if pending_imports:
        titles = ", ".join(f"« {r['title']} »" for r in pending_imports)
        print(
            f"[AVERTISSEMENT] Import(s) en cours non exporté(s) pour : {titles}. "
            "Ces cartes arriveront sans leurs éléments : termine l'import avant d'exporter si tu les veux."
        )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def load_payload(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        die(f"Fichier introuvable : {path}")
    except json.JSONDecodeError as exc:
        die(f"Fichier JSON invalide : {exc}")
    if payload.get("format") != FORMAT:
        die("Ce fichier n'est pas un export de projet Atlas.")
    if payload.get("version") != FORMAT_VERSION:
        die(f"Version d'export non supportée : {payload.get('version')} (attendu {FORMAT_VERSION}).")
    return payload


def check_conflicts(conn: psycopg.Connection, payload: dict, owner_id) -> list[str]:
    problems = []
    project = payload["project"]

    if conn.execute("SELECT 1 FROM projects WHERE id = %s", (project["id"],)).fetchone():
        problems.append(f"Le projet {project['id']} existe déjà (déjà importé ?).")

    same_title = conn.execute(
        "SELECT id FROM projects WHERE user_id = %s AND lower(title) = lower(%s)",
        (owner_id, project["title"]),
    ).fetchone()
    if same_title:
        problems.append(f"Un projet nommé « {project['title']} » existe déjà pour ce propriétaire ({same_title['id']}).")

    map_ids = [m["id"] for m in payload["maps"]]
    if map_ids:
        n = conn.execute("SELECT count(*) AS n FROM maps WHERE id = ANY(%s::uuid[])", (map_ids,)).fetchone()["n"]
        if n:
            problems.append(f"{n} carte(s) de cet export existent déjà.")

    feature_ids = [f["id"] for f in payload["features"]]
    if feature_ids:
        n = conn.execute(
            "SELECT count(*) AS n FROM features WHERE id = ANY(%s::uuid[])", (feature_ids,)
        ).fetchone()["n"]
        if n:
            problems.append(f"{n} élément(s) de cet export existent déjà.")

    for m in payload["maps"]:
        rel = m.get("reference_image_path")
        if rel and (MEDIA_ROOT / rel).exists():
            problems.append(f"Le fichier d'image de référence {rel} existe déjà.")

    return problems


def insert_row(conn: psycopg.Connection, table: str, row: dict) -> None:
    # Table names come from this script only, never from the file
    conn.execute(
        f"INSERT INTO {table} SELECT * FROM jsonb_populate_record(NULL::{table}, %s)",
        (Jsonb(row),),
    )


def import_project(args: argparse.Namespace) -> None:
    payload = load_payload(args.file)
    project = payload["project"]
    maps = payload["maps"]
    features = payload["features"]
    images = payload.get("reference_images", {})

    with connect() as conn:
        missing = sorted(set(payload.get("schema_migrations", [])) - set(applied_migrations(conn)))
        if missing:
            die(
                "La base cible n'a pas toutes les migrations de la base source : "
                + ", ".join(missing)
                + ". Déploie la dernière version avant d'importer."
            )

        owner = conn.execute("SELECT id FROM users WHERE username = %s", (args.owner,)).fetchone()
        if not owner:
            die(
                f"L'utilisateur « {args.owner} » n'existe pas dans la base. "
                "Il doit s'être connecté au moins une fois à la plateforme."
            )

        problems = check_conflicts(conn, payload, owner["id"])
        if problems:
            die("Import annulé :\n  - " + "\n  - ".join(problems))

        print("\nProjet à importer :")
        print(f"  Titre         : {project['title']}")
        print(f"  Exporté le    : {payload.get('exported_at', '?')} (par {payload.get('source_owner') or '?'})")
        print(f"  Contenu       : {len(maps)} carte(s), {len(features)} élément(s), {len(images)} image(s) de référence")
        print(f"  Propriétaire  : {args.owner}")
        if not args.yes and ask("\nConfirmer l'import ? (o/N) : ").lower() not in ("o", "oui", "y", "yes"):
            die("Annulé.")

        project["user_id"] = str(owner["id"])
        written: list[Path] = []
        try:
            with conn.transaction():
                insert_row(conn, "projects", project)
                for m in maps:
                    insert_row(conn, "maps", m)
                for f in features:
                    insert_row(conn, "features", f)

                # Files last, still inside the transaction: a failure rolls the
                # rows back and the files already written are removed below.
                for m in maps:
                    rel = m.get("reference_image_path")
                    image = images.get(m["id"])
                    if not rel or not image:
                        continue
                    target = (MEDIA_ROOT / rel).resolve()
                    if MEDIA_ROOT.resolve() not in target.parents:
                        raise ValueError(f"Chemin d'image de référence invalide : {rel}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(base64.b64decode(image["data"]))
                    written.append(target)
        except Exception as exc:
            for path in written:
                path.unlink(missing_ok=True)
            die(f"Import annulé, rien n'a été modifié : {exc}")

    print(f"\n[OK] Projet « {project['title']} » importé pour « {args.owner} » (id {project['id']}).")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Export / import d'un projet Atlas.")
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Exporter un projet dans un fichier JSON")
    exp.add_argument("--project-id", help="UUID du projet (sinon liste interactive)")
    exp.add_argument("--out-dir", default="/exports", help="Dossier de sortie")
    exp.set_defaults(func=export_project)

    imp = sub.add_parser("import", help="Importer un fichier JSON d'export")
    imp.add_argument("file", help="Fichier JSON produit par l'export")
    imp.add_argument("--owner", default="demo", help="Utilisateur propriétaire (défaut : demo)")
    imp.add_argument("-y", "--yes", action="store_true", help="Ne pas demander de confirmation")
    imp.set_defaults(func=import_project)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
