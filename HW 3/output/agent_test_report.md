# HW 3 Problem 3 — Agent test report

The agent (`agent.py`) was run through Portkey on the four test photos in
`data/test_images/`. Each filename says whether a Campus Customs product
really appears in the shot (`true` / `false`).

## Evaluation results

| Photo | Label | product_found | product_id / possible ids | Confidence | Candidates checked | images_sent | Correct? |
|---|---|---|---|---|---|---|---|
| image_01_true.jpeg | true | true | `yale-dad-t-shirt` | high | 5 | 7 | ✅ |
| image_02_false.jpeg | false | false | — | high | 0 | 1 | ✅ |
| image_03_true.jpeg | true | true | `dry-zone-long-sleeve` | high | 5 | 7 | ✅ |
| image_04_false.jpeg | false | false | — | high | 0 | 1 | ✅ |

**4 / 4 correct** on product presence. Neither run left any ambiguous
`possible_product_ids`.

Candidates the agent checked in each positive run:

- **image_01_true:** yale-dad-t-shirt, tri-blend-sports-baseball-t-shirt,
  tri-blend-sports-football-t-shirt, tri-blend-sports-soccer-t-shirt,
  yale-diving-t-shirt
- **image_02_false** and **image_04_false** stopped after the first look
  (1 image sent). No Yale-branded clothing was seen, so no catalog
  comparison ran.
- **image_03_true:** dry-zone-long-sleeve, yale-maplehouse-diana-mockneck,
  ua-mens-tech-l-s-2-0, squash-left-chest-tennis,
  school-of-management-crest-t-shirt

## Final run (produces `output/identify_product.json`)

```
$ python agent.py --image "data/test_images/image_01_true.jpeg"
data/test_images/image_01_true.jpeg: FOUND yale-dad-t-shirt (Yale Dad T-Shirt) [high confidence]
The customer is wearing the Yale Dad T-Shirt. Its grey short-sleeve construction and distinctive YALE UNIVERSITY DAD front design match exactly; the other candidates say YALE BASEBALL, FOOTBALL, SOCCER, or DIVING.
Checked 5 shortlisted products, 7 images sent.
Saved to /home/user/AI-Foundations/HW 3/output/identify_product.json
```

## Code fixes

None. All five runs (four evaluation runs and the final run) finished with
exit code 0, and no code or prompt changes were made.
