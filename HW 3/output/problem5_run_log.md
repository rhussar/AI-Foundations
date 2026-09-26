# Problem 5 run log

Raw output from running the agent through Portkey. No code or prompts were changed for these runs.

## Graded run: ad effectiveness (student profile)

Command: `python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"`

```
data/videos/ad_humble.mp4 for Maya Chen, Yale sophomore (profiles/profile_student.json): 5/10, might shop [high confidence]
  The ad could stop Maya’s scroll because the muted palette, hoodie styling, and collective Yale identity feel more fashion-led than a standard bookstore commercial. But it currently gives her no reason to choose Campus Customs, no price or student offer, and no way to buy, so add clear branding, a mobile CTA, and a distinctive fit or event-focused product story.
  9 frames, audio NOT analysed, 25.0s, 7,419 input / 1,800 output tokens

Saved 1 result(s) to /home/user/AI-Foundations/HW 3/output/ad_effectiveness.json
```

`video_analysis.audio_analyzed` came out **false**. `audio_note`: The soundtrack could not be analysed (ModelHTTPError: status_code: 400, model_name: gpt-5.6-luna, body: {'message': "azure-openai error: Invalid 'messages[1]'. Content blocks are expected to be either text or image_url type.", 'type': 'invalid_request_error', 'param': 'messages[1]', 'code': 'invalid_value'}).

## Regression check: photo identification

Command: `python agent.py --image data/test_images/image_03_true.jpeg data/test_images/image_04_false.jpeg --out /tmp/id_check.json` (scratch output, `output/identify_product.json` not overwritten)

```
data/test_images/image_04_false.jpeg: NO Campus Customs product [high confidence]
  No Yale-branded clothing is being worn in this photo, so no Campus Customs product appears.
  0 products shortlisted, 1 images sent, 2.4s, 2,163 input / 100 output tokens
data/test_images/image_03_true.jpeg: FOUND dry-zone-long-sleeve (Yale Bulldogs Dry Zone Long-Sleeve Shirt) [high confidence]
  The garment clearly matches the Yale Bulldogs Dry Zone Long-Sleeve Shirt: navy long-sleeve construction and centered solid white YALE over BULLDOGS lettering.
  5 products shortlisted, 7 images sent, 3.1s, 5,422 input / 278 output tokens

Saved 2 result(s) to /tmp/id_check.json
```

Full JSON of `/tmp/id_check.json`:

```json
[
  {
    "image_path": "data/test_images/image_03_true.jpeg",
    "product_found": true,
    "product_id": "dry-zone-long-sleeve",
    "product_name": "Yale Bulldogs Dry Zone Long-Sleeve Shirt",
    "possible_product_ids": [],
    "confidence": "high",
    "evidence": [
      "The customer is wearing a navy long-sleeve performance-style shirt.",
      "The front has large solid white block 'YALE' lettering with smaller 'BULLDOGS' directly underneath, centered on the chest.",
      "It lacks the outlined YALE, standalone Y, Under Armour logo, and additional layout of ua-mens-tech-l-s-2-0.",
      "It is not the cream mockneck, left-chest Yale Squash design, or short-sleeve School of Management shirt."
    ],
    "summary": "The garment clearly matches the Yale Bulldogs Dry Zone Long-Sleeve Shirt: navy long-sleeve construction and centered solid white YALE over BULLDOGS lettering.",
    "observed_garments": [
      {
        "worn_by": "man raising his arm",
        "garment_type": "long-sleeve t-shirt",
        "base_color": "navy",
        "visible_text": [
          "YALE",
          "BULLDOGS"
        ],
        "graphics": [],
        "design_placement": "center chest",
        "has_yale_branding": true
      }
    ],
    "candidates_checked": [
      "dry-zone-long-sleeve",
      "yale-maplehouse-diana-mockneck",
      "ua-mens-tech-l-s-2-0",
      "squash-left-chest-tennis",
      "school-of-management-crest-t-shirt"
    ],
    "images_sent": 7
  },
  {
    "image_path": "data/test_images/image_04_false.jpeg",
    "product_found": false,
    "product_id": null,
    "product_name": null,
    "possible_product_ids": [],
    "confidence": "high",
    "evidence": [
      "Garments seen: Balenciaga.",
      "None of them shows Yale branding."
    ],
    "summary": "No Yale-branded clothing is being worn in this photo, so no Campus Customs product appears.",
    "observed_garments": [
      {
        "worn_by": "woman raising her arms",
        "garment_type": "t-shirt",
        "base_color": "navy blue",
        "visible_text": [
          "Balenciaga"
        ],
        "graphics": [
          "Balenciaga logo"
        ],
        "design_placement": "left chest",
        "has_yale_branding": false
      }
    ],
    "candidates_checked": [],
    "images_sent": 1
  }
]
```
