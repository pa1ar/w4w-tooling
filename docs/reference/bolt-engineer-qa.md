# Bolt Engineer Q&A

Answers provided by Bolt engineer regarding scooter telemetry data format and hardware.

## Timestamps

- `timestamp` field = milliseconds since scooter boot. No correlation to absolute time; zero is first value.
- `gpsInfo` timestamps are accurate (absolute time).
- Timing drift between sensors: insignificant within a ride, <1ms.

## Units

- **Speed** (`currentSpeed`, `gpsInfo.speed`): 1/10 km/h. So value of 250 = 25.0 km/h.
- **Acceleration** (`accelerationCoord` x,y,z triplets): 1/1000 G (milligravity).
- **GPS**: WGS84 coordinate system.

## IMU / Accelerometer

- Mounted rigidly (screwed in, PCB fixed on front panel).
- Orientation: roughly horizontal. X = forward/back, Y = left/right, Z = up/down.
- Sampling rate: 30 Hz (30 datapoints per second), consistent across all scooters.
- Data is raw, no processing or filtering applied.

## GPS

- Typical accuracy: 1-2 meters, can be up to 10m (rare).
- Dragons have better GPS accuracy; Cobras ~2x worse, less sensitive.
- No interpolation when signal is poor — data is raw.
- `gpsFix=true` means GPS can estimate position; `false` means no GPS data.

## Camera / Footage

- Initial capture interval: 500ms (2 fps).
- Changed to 800ms starting May 22, 2025.
- Camera mounted in portrait position, 30 degrees down from horizon.
- FOV: ~122 degrees (long side), standard FullHD resolution.
- Quality flag: new camera recording ID within same photos folder = camera restarted.

## Scooter Hardware

- **Cobras**: 10" wheels front and rear, tubeless, 3-3.5 bar pressure. No suspension.
- **Dragons**: 12" front wheel, 10" rear, tubeless, 3-3.5 bar. Front suspension only.
- Speed limit: 25 km/h in town. Friday evenings limited to 15 km/h (not affecting our data — rides ended earlier).
- Model variants (cobra2, dragon_1_08) are revisions with no significant sensor changes.

## Data Correlation

- `ride_data.json` is the key file for correlating rides, footage, and telemetry.
- Photo folder order_id maps to telemetry filename prefix.
- No known way to identify when scooters are carried vs ridden.

## Source

Direct communication with Bolt engineering team, project partnership context.
