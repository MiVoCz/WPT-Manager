# WPT-Manager

## Local map configuration

Copy `data/config.example.json` to `data/config.json` and set your Mapy.com
REST API key:

```json
{
  "mapy_api_key": "your-api-key"
}
```

`data/config.json` is ignored by Git and must remain local. Without the key,
the map automatically uses OpenStreetMap.
