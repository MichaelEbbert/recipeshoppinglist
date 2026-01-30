# Recipe Shopping List Application

A home application for managing family recipes and generating smart shopping lists.

## Overview

This is a local web application that runs on a home PC and is accessible from any device on the local network (computers, phones, tablets). It helps families plan meals and create efficient shopping lists by aggregating ingredients across multiple recipes and converting them to practical shopping units.

## Core Features

### 1. Recipe Management
- Store a list of family recipes with ingredients and quantities
- Each recipe has a name, optional description, and a list of ingredients
- Ingredients include: name, quantity, and unit (e.g., "2 tbsp butter")
- Add, edit, and delete recipes

### 2. Meal Planning / Recipe Selection
- Web page displaying all saved recipes
- Select multiple recipes for an upcoming shopping trip
- Selected recipes are used to generate the shopping list

### 3. Ingredient Aggregation
- Combine ingredients across all selected recipes
- Sum quantities of the same ingredient (e.g., 2 tbsp butter + 3 tbsp butter = 5 tbsp butter)
- Handle unit normalization at calculation time only (convert to common unit for summing)
- **Important**: Recipes store ingredients exactly as written (e.g., "4 tbsp butter" not "1/4 cup butter"). Conversions happen only during aggregation and shopping list generation, never in storage.

### 4. Shopping Unit Conversion
- Convert aggregated ingredients to practical shopping units
- Examples:
  - Tablespoons of butter → sticks or packs of butter
  - Teaspoons of vanilla → bottles of vanilla extract
  - Cups of flour → bags of flour
- Round up to purchasable quantities (can't buy 1/3 of an egg)

### 5. Inventory Check
- Display all needed ingredients with input fields
- User enters how much of each ingredient they have on hand
- System calculates the difference

### 6. Shopping List Generation
- Generate final shopping list showing only what needs to be purchased
- Display in shopping-friendly units
- If short by a small amount, round up to the smallest purchasable unit
- Example: Need 1 tbsp butter, have none → "Buy 1 pack of butter"

### 7. Recipe Discovery
- Page showing recipe suggestions from external web sources
- Sources should be easy to parse (e.g., AllRecipes, Tasty, BBC Good Food)
- "Add to my recipes" button to save a suggested recipe to the family list
- "Show more" button to fetch new suggestions

### 8. Printing
- Print-friendly recipe view
- Target max 67 lines per recipe (single page on household printer)
- Clean layout: recipe name, ingredients, instructions - no UI chrome

## Design Principles

### Store As-Written, Convert On-Demand
Recipe ingredients are stored exactly as written (e.g., "4 tbsp butter", "1 cup flour"). This ensures:
- Recipe display is a simple read with no transformation
- Original recipe formatting is preserved
- No precision loss from premature conversion
- Conversion logic is isolated to aggregation/shopping calculations

Unit conversion only happens when:
- Aggregating ingredients across selected recipes
- Calculating shopping quantities
- Comparing needed amounts against on-hand inventory

## Technical Requirements

### Architecture
- Local web server running on home PC
- Web-based UI accessible via browser from any device on local network
- Access via local IP address (e.g., `http://192.168.1.142:PORT`)
- No authentication required (trusted home network)

### Database
- SQLite single-file database
- Simple, no separate database server to maintain
- Easy to backup (copy one file)
- Stored in the application directory

### Tech Stack
**Backend:**
- Python 3.11+
- FastAPI (async web framework)
- Jinja2 (server-side templates)
- SQLite via `aiosqlite` (async SQLite access)
- Uvicorn (ASGI server with hot reload for development)

**Frontend:**
- Server-rendered HTML via Jinja2 templates
- HTMX for dynamic updates without writing JavaScript
- Minimal CSS (simple, functional styling)
- Print-friendly recipe view (target: 67 lines max per recipe for printer compatibility)

**Live Updates:**
- HTMX polling (`hx-trigger="every 5s"`) for near-real-time sync
- When one user updates a recipe, others see it within ~5 seconds
- Simple approach, no WebSocket complexity needed

### Unit Conversion System
Needs a comprehensive mapping of:
- Cooking units (tsp, tbsp, cup, oz, lb, ml, L, g, kg, etc.)
- Shopping units (pack, stick, bottle, bag, can, bunch, etc.)
- Ingredient-specific conversions (e.g., 1 stick butter = 8 tbsp = 1/2 cup)

### Data Model

**Recipe**
- id
- name
- description (optional)
- source (optional - URL if imported)
- ingredients[]

**Ingredient** (stored exactly as written in recipe)
- name
- quantity
- unit (as specified in recipe, e.g., "tbsp", "cup", "cloves")

**Shopping Unit Mapping**
- ingredient category
- cooking unit
- shopping unit
- conversion factor

## User Workflow

1. **Setup**: Add family's favorite recipes to the system
2. **Plan**: Before shopping, select recipes for the week
3. **Review**: See aggregated ingredient list
4. **Inventory**: Enter what's already in the pantry/fridge
5. **Shop**: Get final shopping list in store-friendly format
6. **Discover**: Browse suggested recipes and add new ones to try
