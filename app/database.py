import aiosqlite
from pathlib import Path

DATABASE_PATH = Path(__file__).parent.parent / "data" / "recipes.db"


async def get_db():
    """Get database connection."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """Initialize database tables."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                instructions TEXT,
                source_url TEXT,
                complexity TEXT DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity REAL,
                unit TEXT,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shopping_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS unit_conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_unit TEXT NOT NULL,
                to_unit TEXT NOT NULL,
                factor REAL NOT NULL,
                ingredient_category TEXT
            );

            CREATE TABLE IF NOT EXISTS shopping_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_pattern TEXT NOT NULL,
                shopping_unit TEXT NOT NULL,
                unit_size REAL NOT NULL,
                base_unit TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ingredients_recipe ON ingredients(recipe_id);
            CREATE INDEX IF NOT EXISTS idx_shopping_selections_recipe ON shopping_selections(recipe_id);
        """)
        await db.commit()

        # Migration: add complexity column if it doesn't exist
        try:
            await db.execute("ALTER TABLE recipes ADD COLUMN complexity TEXT DEFAULT 'medium'")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Migration: add favorite column if it doesn't exist
        try:
            await db.execute("ALTER TABLE recipes ADD COLUMN favorite INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # Column already exists

        # Seed default unit conversions if empty
        cursor = await db.execute("SELECT COUNT(*) FROM unit_conversions")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await seed_unit_conversions(db)


async def seed_unit_conversions(db):
    """Seed default unit conversions."""
    conversions = [
        # Volume conversions (to teaspoons as base)
        ("tbsp", "tsp", 3, None),
        ("cup", "tsp", 48, None),
        ("cup", "tbsp", 16, None),
        ("pint", "cup", 2, None),
        ("quart", "cup", 4, None),
        ("gallon", "cup", 16, None),
        ("fl oz", "tbsp", 2, None),
        ("ml", "tsp", 0.202884, None),
        ("liter", "cup", 4.22675, None),

        # Weight conversions (to ounces as base)
        ("lb", "oz", 16, None),
        ("g", "oz", 0.035274, None),
        ("kg", "oz", 35.274, None),

        # Butter specific
        ("stick", "tbsp", 8, "butter"),
        ("stick", "cup", 0.5, "butter"),
    ]

    await db.executemany(
        "INSERT INTO unit_conversions (from_unit, to_unit, factor, ingredient_category) VALUES (?, ?, ?, ?)",
        conversions
    )

    # Seed shopping units
    shopping_units = [
        ("butter", "stick", 8, "tbsp"),
        ("flour", "bag (5 lb)", 80, "cup"),
        ("sugar", "bag (4 lb)", 9, "cup"),
        ("milk", "gallon", 16, "cup"),
        ("egg%", "dozen", 12, "unit"),
        ("vanilla%", "bottle (2 oz)", 12, "tsp"),
        ("olive oil%", "bottle (16 oz)", 32, "tbsp"),
        ("vegetable oil%", "bottle (48 oz)", 96, "tbsp"),
    ]

    await db.executemany(
        "INSERT INTO shopping_units (ingredient_pattern, shopping_unit, unit_size, base_unit) VALUES (?, ?, ?, ?)",
        shopping_units
    )

    await db.commit()
