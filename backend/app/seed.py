from datetime import date
from sqlalchemy import select
from app.db.session import SessionLocal, Base, engine
from app.models import (
    District, Block, Cluster, School, AcademicYear, Translation, Menu, Ingredient, Recipe,
    UserSchoolAccess, SchoolProfile, StockTransaction
)

TRANSLATIONS = [
    ("app.title", "PM POSHAN", "पीएम पोषण"),
    ("dashboard", "Dashboard", "डॅशबोर्ड"),
    ("attendance", "Attendance", "उपस्थिती"),
    ("daily_meal", "Daily Meal", "दैनिक आहार"),
    ("stock", "Stock", "साठा"),
    ("reports", "Reports", "अहवाल"),
    ("submit", "Submit", "सादर करा"),
    ("approve", "Approve", "मंजूर करा"),
    ("language", "Language", "भाषा"),
]

MENUS = [
    ("VPUL-W13-MON","Vegetable Pulao","व्हेज पुलाव","W13",1),
    ("MDKH-W13-TUE","Moong Dal Khichdi","मुगडाळ खिचडी","W13",2),
    ("CHPUL-W13-WED","Chana Pulao","चना पुलाव","W13",3),
    ("MBHAT-W13-THU","Masale Bhat","मसाले भात","W13",4),
    ("CHKH-W13-FRI","Chawli Khichdi","चवळी खिचडी","W13",5),
    ("MUSAL-W13-SAT","Matki Usal","मटकी उसळ","W13",6),
    ("MTPUL-W24-MON","Matar Pulao","मटर पुलाव","W24",1),
    ("MDVB-W24-TUE","Moong Drumstick Varan Bhat","मुग शेवगा वरणभात","W24",2),
    ("SOYP-W24-WED","Soya Pulao","सोया पुलाव","W24",3),
    ("VPUL-W24-THU","Vegetable Pulao","व्हेज पुलाव","W24",4),
    ("MDKH-W24-FRI","Moong Dal Khichdi","मुगडाळ खिचडी","W24",5),
    ("MASP-W24-SAT","Masoor Pulao","मसुरी पुलाव","W24",6),
]

INGREDIENTS = [
    ("RICE","Rice","तांदूळ","CEREAL_PULSE","KG",True),
    ("MOONGDAL","Moong Dal","मुगडाळ","CEREAL_PULSE","KG",True),
    ("TURDAL","Tur Dal","तूरडाळ","CEREAL_PULSE","KG",True),
    ("MASOORDAL","Masoor Dal","मसूरडाळ","CEREAL_PULSE","KG",True),
    ("MATKI","Matki","मटकी","SPROUT","KG",True),
    ("MOONG","Moong","मूग","SPROUT","KG",True),
    ("CHAWLI","Chawli","चवळी","SPROUT","KG",True),
    ("HARBHARA","Harbhara","हरभरा","SPROUT","KG",True),
    ("VATANA","Peas","वाटाणा","SPROUT","KG",True),
    ("SOYA","Soyabean","सोयाबीन","SPROUT","KG",True),
    ("CUMIN","Cumin","जिरे","SPICE","KG",True),
    ("MUSTARD","Mustard","मोहरी","SPICE","KG",True),
    ("TURMERIC","Turmeric","हळद","SPICE","KG",True),
    ("GARAM","Garam Masala","गरम मसाला","SPICE","KG",True),
    ("OIL","Oil","तेल","CONSUMABLE","L",True),
    ("SALT","Salt","मीठ","CONSUMABLE","KG",True),
    ("SUGAR","Sugar/Jaggery","साखर/गुळ","CONSUMABLE","KG",True),
    ("MILK","Milk Powder","दूध पावडर","CONSUMABLE","KG",True),
    ("RAGI","Ragi","नाचणी","CONSUMABLE","KG",True),
    ("EGG","Eggs","अंडी","OTHER","EA",True),
    ("VEGETABLE","Vegetable Cost","भाजीपाला खर्च","OTHER","INR",False),
    ("FUEL","Fuel Cost","इंधन खर्च","OTHER","INR",False),
]


# Demo/configurable recipe quantities in the ingredient base unit per student.
# These values are sample system configuration for testing, not a claim of official entitlement norms.
RECIPE_BASE = {
    "RICE": (0.100, 0.150),
    "OIL": (0.005, 0.0075),
    "SALT": (0.002, 0.003),
}
MENU_EXTRAS = {
    "VPUL-W13-MON": [("VATANA", 0.020, 0.030)],
    "MDKH-W13-TUE": [("MOONGDAL", 0.020, 0.030)],
    "CHPUL-W13-WED": [("HARBHARA", 0.020, 0.030)],
    "MBHAT-W13-THU": [("TURDAL", 0.020, 0.030)],
    "CHKH-W13-FRI": [("CHAWLI", 0.020, 0.030)],
    "MUSAL-W13-SAT": [("MATKI", 0.035, 0.050)],
    "MTPUL-W24-MON": [("VATANA", 0.020, 0.030)],
    "MDVB-W24-TUE": [("MOONGDAL", 0.020, 0.030)],
    "SOYP-W24-WED": [("SOYA", 0.020, 0.030)],
    "VPUL-W24-THU": [("VATANA", 0.020, 0.030)],
    "MDKH-W24-FRI": [("MOONGDAL", 0.020, 0.030)],
    "MASP-W24-SAT": [("MASOORDAL", 0.020, 0.030)],
}
DEMO_OPENING = {
    "RICE": 200, "MOONGDAL": 40, "TURDAL": 40, "MASOORDAL": 40, "MATKI": 40,
    "MOONG": 30, "CHAWLI": 40, "HARBHARA": 40, "VATANA": 40, "SOYA": 40,
    "CUMIN": 10, "MUSTARD": 10, "TURMERIC": 10, "GARAM": 10, "OIL": 50,
    "SALT": 40, "SUGAR": 30, "MILK": 20, "RAGI": 30, "EGG": 500,
}

def main():
    # Production-safe bootstrap.
    Base.metadata.create_all(bind=engine)
    print("Production-safe bootstrap complete: schema ensured; no demo data seeded.")

if __name__ == "__main__":
    main()
