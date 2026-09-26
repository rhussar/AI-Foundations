"""Problem 6: build the customer profiles from the CustomerProfile model and save them as JSON.

Writing the files from model instances means they always match models.py; a typo in a field name
fails here instead of silently dropping information from the ad judgement.

Run with:  python make_profiles.py
"""

from models import CustomerProfile
from tools import ROOT


PROFILES_DIR = ROOT / "profiles"

STUDENT = CustomerProfile(
    profile_id="student",
    name="Maya Chen, Yale sophomore",
    description=(
        "A 19-year-old Yale College sophomore living in Pierson College. She's proud to be at Yale but doesn't "
        "want to look like a tourist in generic campus gear. She buys clothes mostly on her phone, follows what "
        "her friends and classmates wear, and cares whether something feels current rather than dated."
    ),
    age_range="18-22",
    relationship_to_yale="current undergraduate, lives on campus",
    interests=[
        "intramural soccer",
        "a cappella",
        "going to Yale-Harvard football games",
        "thrifting and streetwear",
        "TikTok and Instagram trends",
    ],
    values=[
        "belonging to her residential college and friend group",
        "authentic, not try-hard",
        "supporting local and student-run businesses",
        "value for money",
    ],
    style="oversized hoodies and crewnecks, muted colors, streetwear with a vintage feel; avoids loud, touristy logo gear",
    budget="about $40-60 a month on clothes from a campus job; will stretch for a piece she'll wear constantly",
    price_sensitivity="high",
    shopping_habits=[
        "buys on her phone after seeing something on social media",
        "waits for student discounts or drops",
        "buys matching gear with friends for events like The Game",
    ],
    media_habits=[
        "TikTok daily",
        "Instagram stories and reels",
        "skips ads that feel corporate within two seconds",
        "watches with sound on when the music is good",
    ],
    already_owns=["one grey Yale crewneck from the bookstore", "a Pierson College tee from freshman year"],
    buys_for=["herself", "her friend group, for matching event gear"],
    purchase_occasions=[
        "The Game (Yale-Harvard football)",
        "residential college spirit days",
        "start of term",
        "when the weather turns cold",
    ],
    buying_triggers=[
        "seeing classmates she admires wearing it",
        "limited drops and event gear (The Game, college spirit days)",
        "a clear student discount or easy pickup on campus",
        "designs that feel like insider Yale, not tourist Yale",
    ],
    likely_objections=[
        "already has a Yale sweatshirt",
        "doesn't know Campus Customs or how it differs from the Yale bookstore",
        "too expensive on a student budget",
        "cringe or try-hard marketing",
    ],
)

PARENT = CustomerProfile(
    profile_id="parent",
    name="Tom Brennan, father of a Yale sophomore",
    description=(
        "A 53-year-old dad from suburban Columbus, Ohio, whose daughter is a Yale sophomore. Nobody in the "
        "family went to Yale before her, and he's openly proud of it. He visits campus two or three times a year, "
        "buys Yale gear for himself and as gifts, and wants it to look good and last, without embarrassing his "
        "daughter."
    ),
    age_range="48-58",
    relationship_to_yale="parent of a current undergraduate; didn't attend Yale himself; lives an 8-hour drive away",
    interests=[
        "college football",
        "following his daughter's a cappella performances online",
        "golf",
        "family road trips to New Haven",
    ],
    values=[
        "pride in his daughter's achievement",
        "quality that lasts",
        "tradition and belonging to the Yale family",
        "not embarrassing his daughter",
    ],
    style="classic and comfortable: quarter-zips, crewnecks and polos in navy or grey; no streetwear or oversized fits",
    budget="happy to pay $60-120 for something he'll wear for years; spends more on holiday gifts",
    price_sensitivity="low",
    shopping_habits=[
        "buys online from shops he trusts, checking reviews, sizing and the return policy",
        "shops in person on campus during visits",
        "orders gifts in November and December",
    ],
    media_habits=[
        "Facebook daily, including the Yale parents group",
        "reads email newsletters from brands he's bought from",
        "YouTube for sports highlights",
        "scrolls Facebook videos with the sound off",
        "doesn't follow rap or current music trends",
    ],
    already_owns=["a Yale Parent car magnet", "a navy Yale cap from the bookstore"],
    buys_for=["himself", "his wife", "the grandparents, as gifts", "his daughter, in care packages"],
    purchase_occasions=["Family Weekend in October", "the holidays", "move-in day", "Commencement", "The Game"],
    buying_triggers=[
        "'Yale Dad' and other family designs made for parents",
        "recommendations in the Yale parents Facebook group",
        "seeing the product clearly: fabric, fit and price",
        "easy shipping to home or to campus, and gift-ready options",
    ],
    likely_objections=[
        "the ad seems aimed at students, not at him",
        "can't tell who the shop is or whether the gear is good quality",
        "no product details, price or place to buy",
        "worries his daughter would find it embarrassing",
        "doesn't get the music or pop-culture references",
    ],
)


def main():
    PROFILES_DIR.mkdir(exist_ok=True)
    for profile in (STUDENT, PARENT):
        path = PROFILES_DIR / f"profile_{profile.profile_id}.json"
        path.write_text(profile.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
