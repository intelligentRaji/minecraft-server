# Modrinth API Reference for Mod Management

This reference documents the endpoints, payload formats, and query conventions used by the `minecraft-mod-manager` skill.

---

## 1. Version Query Endpoint

```http
GET https://api.modrinth.com/v2/project/{id|slug}/version?game_versions=["1.20.1"]&loaders=["forge"]
```

### Headers
* `User-Agent`: Always supply a descriptive User-Agent (e.g. `Antigravity/1.0`).

### Response Structure (Array of Version Objects)
```json
[
  {
    "id": "version_id",
    "project_id": "project_id",
    "version_number": "1.4.11",
    "game_versions": ["1.20.1"],
    "loaders": ["forge"],
    "files": [
      {
        "url": "https://cdn.modrinth.com/data/.../mod.jar",
        "filename": "mod.jar",
        "primary": true,
        "size": 1234567
      }
    ],
    "dependencies": [
      {
        "version_id": null,
        "project_id": "dependency_project_id",
        "dependency_type": "required"
      }
    ]
  }
]
```

---

## 2. Project Lookup Endpoint

To resolve a dependency `project_id` to its human-readable name or slug:

```http
GET https://api.modrinth.com/v2/project/{id}
```

---

## 3. Automated Tooling Reference

Use the bundled script instead of raw HTTP calls when possible:

```bash
# Query mod metadata:
python3 .agents/skills/minecraft-mod-manager/scripts/query_modrinth.py <slug>

# Query and directly download to target category folder:
python3 .agents/skills/minecraft-mod-manager/scripts/query_modrinth.py <slug> --download-to modpack/server-client
```
