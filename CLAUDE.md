# Recipe Shopping List Application

## AWS Deployment Info

- **Subdomain:** https://recipeshoppinglist.mebbert.com
- **Internal Port:** 3003
- **Status:** Active

### SSH Access
```bash
ssh -i "C:\claude_projects\taskschedule\taskschedule-key.pem" ec2-user@100.50.222.238
```

### Server Documentation
Full deployment docs on server: `/home/ec2-user/taskschedule/AWS_DEPLOYMENT.md`

### Nginx Config
Already configured in `/etc/nginx/conf.d/subdomains.conf` to proxy to port 3003.

### Deploy

Use the centralized deployment scripts in `C:\claude_projects\deployment-manager\`:

```bash
cd C:\claude_projects\deployment-manager
python deploy.py recipeshoppinglist       # Full deploy (sync + deps + restart)
python status.py recipeshoppinglist       # Health check
python restart.py recipeshoppinglist      # Quick restart
python logs.py recipeshoppinglist -f      # Follow logs
```

---

## TODO: Nginx-Level Authentication

Secure all apps (tifootball, sevenhabitslist, recipeshoppinglist) at the nginx layer using `auth_request` module with a shared auth service.

### Changes Required

1. **Create auth service** (`/home/ec2-user/auth-service/`)
   - Simple FastAPI app on port 3010 (internal only)
   - Endpoints:
     - `GET /auth/check` - returns 200 if session cookie valid, 401 if not
     - `GET /auth/login` - renders login page
     - `POST /auth/login` - validates credentials, sets session cookie
     - `GET /auth/logout` - clears session cookie
   - Share user credentials with taskschedule (read from same database or hardcoded family users)

2. **Update nginx config** (`/etc/nginx/conf.d/subdomains.conf`)
   - Add `auth_request` directive to each protected server block:
     ```nginx
     location / {
         auth_request /auth/check;
         error_page 401 = @login_redirect;
         # ... existing proxy_pass ...
     }

     location = /auth/check {
         internal;
         proxy_pass http://127.0.0.1:3010/auth/check;
         proxy_pass_request_body off;
         proxy_set_header Content-Length "";
         proxy_set_header X-Original-URI $request_uri;
         proxy_set_header Cookie $http_cookie;
     }

     location @login_redirect {
         return 302 https://auth.mebbert.com/login?next=$scheme://$host$request_uri;
     }

     location /auth/ {
         proxy_pass http://127.0.0.1:3010/auth/;
         proxy_set_header Host $host;
     }
     ```

3. **Create auth subdomain** (optional, or serve from each app)
   - Option A: Dedicated `auth.mebbert.com` subdomain for login page
   - Option B: Each app serves `/auth/login` via nginx location block (simpler)

4. **DNS and SSL** (if using Option A)
   - Add Route53 A record for `auth.mebbert.com`
   - Run certbot for SSL cert

5. **Session cookie settings**
   - Domain: `.mebbert.com` (shared across all subdomains)
   - Secure: true
   - HttpOnly: true
   - SameSite: Lax

6. **Create systemd service** for auth-service
   - Similar to other apps
   - Add to sudoers for management

### Files to Create/Modify

| File | Action |
|------|--------|
| `/home/ec2-user/auth-service/main.py` | Create - FastAPI auth endpoints |
| `/home/ec2-user/auth-service/templates/login.html` | Create - Login page |
| `/etc/nginx/conf.d/subdomains.conf` | Modify - Add auth_request blocks |
| `/etc/systemd/system/auth-service.service` | Create - systemd unit |
| `/etc/sudoers.d/app-services` | Modify - Add auth-service commands |

### Alternative: Simpler HTTP Basic Auth

If a browser login dialog is acceptable (less pretty but zero code):

```nginx
location / {
    auth_basic "Family Apps";
    auth_basic_user_file /etc/nginx/.htpasswd;
    # ... existing proxy_pass ...
}
```

Create password file:
```bash
sudo htpasswd -c /etc/nginx/.htpasswd username
```

---

A home application for managing family recipes and generating smart shopping lists.

## Overview

This is a local web application that runs on a home PC and is accessible from any device on the local network (computers, phones, tablets). It helps families plan meals and create efficient shopping lists by aggregating ingredients across multiple recipes and converting them to practical shopping units.

## Core Features

### 1. Recipe Management
- Store a list of family recipes with ingredients and quantities
- Each recipe has a name, optional description, and a list of ingredients
- Ingredients include: name, quantity, and unit (e.g., "2 tbsp butter")
- Add, edit, and delete recipes
- Automatic complexity rating (easy/medium/hard) based on ingredient count and steps

**Unsupported unit warning:**
- When saving a recipe with non-standard units (e.g., "package", "bunch"), a red warning appears
- User must click Save a second time to confirm - prevents accidental use of units that won't aggregate properly
- Ingredients with unsupported units will appear on shopping lists but won't combine with other units

**"To taste" ingredients:**
- Just type "salt to taste" as the ingredient name (no quantity/unit)
- These appear on shopping lists as-is without aggregation

**Ingredient parsing:**
- Supports decimals (3.2 lb), fractions (1/2 cup), mixed fractions (1 1/2 cups), and whole numbers
- Parser tries patterns in order: decimals → mixed fractions → simple fractions → whole numbers
- Specific count units are preserved: "3 slices cheese" stays as "3 slice" not "3 count"
- Preserved count units: slice, clove, can, bunch, head, stalk, sprig, leaf, piece

### 2. Meal Planning / Recipe Selection
- Web page displaying all saved recipes with checkboxes
- Select multiple recipes for an upcoming shopping trip
- Simple form-based flow (no HTMX/active content on shopping pages)
- Linear flow: Select recipes → Inventory check → Shopping list → Start over

### 3. Ingredient Aggregation
- Combine ingredients across all selected recipes
- Sum quantities of the same ingredient (e.g., 2 tbsp butter + 3 tbsp butter = 5 tbsp butter)
- Handle unit normalization at calculation time only (convert to common unit for summing)
- **Important**: Recipes store ingredients exactly as written (e.g., "4 tbsp butter" not "1/4 cup butter"). Conversions happen only during aggregation and shopping list generation, never in storage.

### 4. Shopping Unit Conversion
- Convert aggregated ingredients to practical shopping units
- Display quantities as fractions (1/4 cup, 1/2 lb) not decimals
- Round up for shopping bias (need 3/16 lb → show 1/4 lb)

**Volume roll-up rules:**
- tsp/tbsp → cups (when >= 1/8 cup)
- cups → pints (when >= 1 pint)
- pints → quarts (when >= 1 quart)
- quarts → gallons (when >= 1 gallon)

**Weight roll-up rules:**
- oz → lb (when >= 1/8 lb / 2 oz)

**Special handling:**
- Butter: sticks (1 stick = 8 tbsp)
- Eggs: half dozen or dozen
- Flour: bags for large quantities
- Milk: gallons for large quantities

**No metric conversion** - US units only. Users convert at the store if shelf labels show ml/g.

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
- Search for recipes from 4 external sources (queried in parallel):
  - **TheMealDB** - General recipes (free API)
  - **BBC Good Food** - British recipes, good variety
  - **Skinnytaste** - Air fryer and healthy recipes
  - **Hey Grill Hey** - BBQ and grilling recipes
- Results are interleaved from all sources for variety
- Max complexity filter (easy only, medium & below, or all)
- Indian cuisine filtered out per user preference
- "Surprise Me" button for random recipe suggestions
- "View & Add" to preview and import recipes to your collection

### 8. Printing
- Print-friendly recipe view
- Target max 67 lines per recipe (single page on household printer)
- Clean layout: recipe name, ingredients, instructions - no UI chrome

### 9. Complexity Rating
- Automatic rating based on analysis of 595 recipes:
  - **Easy**: ≤16 combined (ingredients + steps)
  - **Medium**: 17-29 combined
  - **Hard**: ≥30 combined
- Displayed as color-coded badges on recipe list, detail, and discover pages
- Filter discovery results by maximum complexity

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

### No Browser Caching
All pages return `Cache-Control: no-store` headers to ensure users always see fresh content. Static files (CSS) are still cached for performance.

## Technical Requirements

### Architecture
- Local web server running on home PC
- Web-based UI accessible via browser from any device on local network
- Access via local IP address (e.g., `http://192.168.1.142:8000`)
- No authentication required (trusted home network)

### Database
- SQLite single-file database (`data/recipes.db`)
- Simple, no separate database server to maintain
- Easy to backup (copy one file)
- Auto-created on first run
- Database file is gitignored - stays on local machine only
- To move to another machine: copy `data/recipes.db` to same location

### Tech Stack
**Backend:**
- Python 3.11+
- FastAPI (async web framework)
- Jinja2 (server-side templates)
- SQLite via `aiosqlite` (async SQLite access)
- Uvicorn (ASGI server with hot reload for development)
- httpx (async HTTP client for recipe discovery)
- BeautifulSoup4 (HTML parsing for recipe scraping)

**Frontend:**
- Server-rendered HTML via Jinja2 templates
- HTMX for dynamic updates without writing JavaScript
- Minimal CSS (simple, functional styling)
- Print-friendly recipe view (target: 67 lines max per recipe)

**Live Updates:**
- HTMX used on discover page for search results
- Shopping flow uses simple form POSTs (no live updates needed)
- Recipe pages are static - refresh to see updates from other users

### Recipe Discovery Sources
All sources are queried via HTTP with no API keys required:
- **TheMealDB**: Free public JSON API
- **BBC Good Food**: HTML scraping with JSON-LD parsing
- **Skinnytaste**: WordPress blog with JSON-LD recipe data
- **Hey Grill Hey**: WordPress blog with JSON-LD recipe data

No AI/LLM tokens used for discovery - just standard HTTP requests.

## Project Structure

```
recipeshoppinglist/
├── CLAUDE.md              # This file
├── requirements.txt       # Python dependencies
├── main.py               # FastAPI app entry point
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── database.py       # SQLite setup, migrations, seeding
│   ├── models.py         # Data classes, complexity calculation
│   ├── unit_converter.py # Unit conversion logic
│   ├── routers/
│   │   ├── recipes.py    # Recipe CRUD endpoints
│   │   ├── shopping.py   # Shopping list flow
│   │   └── discover.py   # Recipe discovery from external sources
│   ├── templates/        # Jinja2 + HTMX templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── recipes/
│   │   ├── shopping/
│   │   └── discover/
│   └── static/
│       └── css/style.css
└── data/                 # Created at runtime
    └── recipes.db        # SQLite database
```

## Data Model

**Recipe**
- id
- name
- description (optional)
- instructions
- source_url (optional - URL if imported)
- complexity (easy/medium/hard)
- created_at, updated_at

**Ingredient** (stored exactly as written in recipe)
- id
- recipe_id
- name
- quantity
- unit (as specified in recipe, e.g., "tbsp", "cup", "cloves")
- sort_order

**Shopping Selections** (legacy - no longer used)
- Shopping flow now uses form POST to pass selected recipe IDs between pages
- No server-side session storage needed

## Running the Application

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

Access at `http://localhost:8000` or `http://<your-local-ip>:8000` from other devices.

## Development Notes

- **Server restart**: Uvicorn's `--reload` flag watches for file changes, but sometimes changes aren't detected. Restart the server manually if code changes don't take effect.
- **Browser caching**: HTML pages have `Cache-Control: no-store` headers, so browser caching shouldn't be an issue. CSS is cached normally.

## User Workflow

1. **Setup**: Add family's favorite recipes to the system
2. **Plan**: Before shopping, select recipes for the week
3. **Review**: See aggregated ingredient list
4. **Inventory**: Enter what's already in the pantry/fridge
5. **Shop**: Get final shopping list in store-friendly format
6. **Discover**: Browse suggested recipes and add new ones to try
