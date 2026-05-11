# OSM Smoothness Classification

Source: https://wiki.openstreetmap.org/wiki/Key:smoothness

## All Values

| Value | Description | Usable by |
|-------|-------------|-----------|
| excellent | As-new asphalt/concrete, seamless paving stones | All wheeled vehicles |
| good | Minor wear (narrow cracks, shallow dents); best brick/sett | Racing bikes and below |
| intermediate | Patched asphalt, wider cracks, small potholes easily avoided | City bikes, wheelchairs, scooters and below |
| bad | Heavily damaged, many potholes, avg speed <50% of smooth | Trekking bikes, normal cars and below |
| very_bad | Unpaved with potholes and ruts, needs 18cm+ clearance | High-clearance cars, light off-road |
| horrible | Ruts and rocks, needs 21cm+ clearance | Heavy off-road vehicles |
| very_horrible | Deep ruts, needs 24cm+ clearance | Tractors, ATVs, mountain bikes |
| impassable | Not passable by vehicles | Hikers only |

## Wheelchair-Relevant Subset

For wheelchair accessibility, only the first 5 values are meaningful:
- **excellent** — fully accessible
- **good** — accessible
- **intermediate** — accessible with difficulty (wheelchair explicitly listed)
- **bad** — not wheelchair accessible
- **very_bad** — not accessible

Values horrible/very_horrible/impassable are off-road terrain, irrelevant for wheelchair routing.

## Our Pipeline

We classify into 5 classes (excellent through very_bad) matching the wheelchair-relevant OSM values.
We propose tags only for ways without existing smoothness.
