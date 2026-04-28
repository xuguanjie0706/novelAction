"""回填 characters 历史 NULL 字段，避免响应校验报错。"""
from app.database import SessionLocal
from app.models import Character


def normalize_character_defaults(char: Character) -> bool:
    changed = False
    if char.alias is None:
        char.alias = []
        changed = True
    if char.arc_stages is None:
        char.arc_stages = []
        changed = True
    if char.known_skills is None:
        char.known_skills = []
        changed = True
    if char.owned_items is None:
        char.owned_items = []
        changed = True
    if char.strengths is None:
        char.strengths = []
        changed = True
    if char.weaknesses is None:
        char.weaknesses = []
        changed = True
    if char.special_traits is None:
        char.special_traits = []
        changed = True
    if char.extra is None:
        char.extra = {}
        changed = True
    if char.current_status is None:
        char.current_status = "alive"
        changed = True
    return changed


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.query(Character).all()
        changed_count = 0
        for row in rows:
            if normalize_character_defaults(row):
                changed_count += 1
        if changed_count:
            db.commit()
        print(f"characters total={len(rows)} changed={changed_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
