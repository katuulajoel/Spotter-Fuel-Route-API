# Spotter Fuel Route API

Plan a driving route in the US, pick fuel stops with the lowest available prices along the path, and report expected fuel spend. Built with Django 4.2.

## 🚀 Features
- Calculate optimal driving routes with fuel stops
- Find the cheapest fuel prices along your route
- Estimate total fuel costs for your journey
- Interactive map visualization

## ⚙️ Prerequisites
- Python 3.8+
- Mapbox Access Token (get one at [Mapbox](https://account.mapbox.com/))
- pip (Python package manager)

## 🛠️ Setup

1. **Create and activate virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Copy the example environment file and update with your credentials:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and add your Mapbox token:
   ```
   MAPBOX_ACCESS_TOKEN=your_mapbox_token_here
   ```
   
   Or export it directly:
   ```bash
   export MAPBOX_ACCESS_TOKEN=your_mapbox_token_here
   ```

4. **Apply database migrations**
   ```bash
   python manage.py migrate
   ```

5. **(Optional) Configure custom paths**
   ```bash
   export FUEL_DATA_PATH=/path/to/fuel_data.csv
   export STATION_CACHE_PATH=/path/to/station_cache.json
   export PRELOAD_STATIONS_ON_START=true           # pre-geocode on startup
   export PRELOAD_STATION_LIMIT=200                # how many stations to geocode at boot
   ```

## 🚦 Running the Application

1. **Start the development server**
   ```bash
   python manage.py runserver 8000
   ```
   The server will be available at `http://localhost:8000`

2. **Access the API**
   - Main endpoint: `POST /api/route/`
   - API documentation: `http://localhost:8000/api/schema/` (if using DRF Spectacular)

3. **Testing with Postman**
   - Import the provided Postman collection: `Spotter-Fuel-Route.postman_collection.json`
   - The collection uses `{{base_url}}` which defaults to `http://localhost:8000`

## Request/Response
Example request:
```bash
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "New York, NY",
    "end": "Chicago, IL",
    "range_miles": 500,
    "mpg": 10,
    "station_radius_miles": 50,
    "allow_station_geocoding": true,
    "geocode_budget_per_stop": 12
  }'
```

Key response fields:
- `route.distance_miles`, `route.duration_minutes`, `route.geometry`, `route.static_map_url`
- `fuel_plan.stops`: mile marker, suggested station (name/address/price/coords) and the coordinate along the route where you would stop
- `fuel_plan.summary`: total gallons, total cost (if prices are known), and per-segment fuel math

## How it works
- Mapbox Directions gives one route/geometry; we also expose a static map URL that draws the route and fuel stops.
- Fuel prices come from `fuel-prices-for-be-assessment.csv`. Coordinates for stations are cached in `data/station_cache.json`.
- For each 0, 500, 1000... mile marker we look for the cheapest station within `station_radius_miles` of that point. If coordinates are missing we optionally geocode the station (budgeted by `geocode_budget_per_stop`) and persist the result. If nothing is nearby, we fall back to the cheapest station with known coordinates.
- Fuel cost is computed per leg using the price at the stop that precedes the leg.

## 📝 Notes & Tips

- **First Run**: Keep `allow_station_geocoding: true` to build the station cache
- **Subsequent Runs**: Disable geocoding to avoid unnecessary Mapbox API calls
- **Django Version**: Currently using Django 4.2.x. To upgrade to Django 5.x, update `requirements.txt`
- **Development**: For local development, you can use the included `.env.example` as a template

## 🐛 Troubleshooting

- **Missing Dependencies**: Run `pip install -r requirements.txt`
- **Database Issues**: Try `python manage.py migrate` to apply pending migrations
- **Mapbox Errors**: Verify your `MAPBOX_ACCESS_TOKEN` is correctly set in your environment

## 📚 API Documentation

For detailed API documentation, visit the interactive API schema at `http://localhost:8000/api/schema/` when the development server is running.
