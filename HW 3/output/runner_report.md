# Catalog build runner report

Result: **99 of 102 products catalogued** in `output/catalog.json`. 3 products could not be described because the Azure OpenAI content filter behind Portkey blocked their photos.

## What ran

- `python portkey_client.py`: OK (gpt-5.6-luna via Portkey replied `ready`).
- `python build_catalog.py --limit 5`: 5 described, 8.6s, 7,530 input / 744 output tokens. Spot-checked against the photos (Big Yale hoodie, Benjamin Franklin 1/4-zip, etc.) and they were accurate.
- Full run (after the blocked canaries were set aside, see below): 94 described in 23.6s, 146,505 input / 14,373 output tokens. Saved 99 entries.
- Two more full runs with all 102 photos in place: both stopped at the canary with the same content-policy error, so the 3 failures persist.

No code was changed. The default `--reasoning-effort` worked.

## The blocker

All three failed with the same error:

```
ModelHTTPError: status_code: 400, model_name: gpt-5.6-luna,
body: {'message': 'azure-openai error: Image processing blocked due to content policy violation.',
       'code': 'content_policy_violation'}
```

| product_id | what the photo shows |
|---|---|
| `benjamin-franklin-t-shirt` | Heather grey tee, full-front Benjamin Franklin College shield + "BENJAMIN FRANKLIN COLLEGE" |
| `berkeley-1-4-zip` | Heather grey quarter-zip, small red Berkeley College shield + "BERKELEY" on the left chest |
| `timothy-dwight-college-crewneck` | Heather grey Port & Company crewneck, small Timothy Dwight shield + "TIMOTHY DWIGHT" on the left chest |

These are ordinary residential-college crest garments, so this is a false positive. It is deterministic: each photo was refused on every attempt, while a photo that had already succeeded went through fine when re-sent in between.

## Side effect of the canary design

`build_catalog.py` sends `todo[0]` alone as a canary and aborts the whole run if it fails. When a blocked photo sorts first among the uncatalogued products, it blocks every other product too. To get past this without editing code, the runner temporarily moved blocked canary photos out of the local, gitignored `data/products/` folder, ran the build, then moved them back. A future run with all photos present will retry only these 3, but it will always stop at the canary (`benjamin-franklin-t-shirt`) while the filter keeps refusing them.

## Options for the parent session (not done here: they are design decisions)

1. Treat a `content_policy_violation` on the canary as a per-item failure instead of aborting, since it proves the key, network and model settings are fine.
2. Try re-encoding or cropping the 3 photos differently before upload (e.g. a different shrink size), which sometimes gets past Azure's image filter.
3. Try another model in `ALLOWED_MODELS`, if one is served by a non-Azure provider.
4. Write the 3 entries by hand from the photos and note that in the README.
