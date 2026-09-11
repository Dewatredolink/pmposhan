from datetime import date
from sqlalchemy import select
from app.db.session import SessionLocal, Base, engine
from app.models import District, Block, Cluster, School, AcademicYear, Translation, Menu, Ingredient, UserSchoolAccess, SchoolProfile

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

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        district = db.scalar(select(District).where(District.code == "PALGHAR"))
        if not district:
            district = District(code="PALGHAR", name_en="Palghar", name_mr="पालघर")
            db.add(district); db.flush()
        block = db.scalar(select(Block).where(Block.code == "MOKHADA"))
        if not block:
            block = Block(code="MOKHADA", district_id=district.id, name_en="Mokhada", name_mr="मोखाडा")
            db.add(block); db.flush()
        cluster = db.scalar(select(Cluster).where(Cluster.code == "SAMPLECL"))
        if not cluster:
            cluster = Cluster(code="SAMPLECL", block_id=block.id, name_en="Sample Cluster", name_mr="नमुना केंद्र")
            db.add(cluster); db.flush()
        school = db.scalar(select(School).where(School.code == "SAMPLE001"))
        if not school:
            school = School(code="SAMPLE001", udise_code="SAMPLE-UDISE", cluster_id=cluster.id,
                            name_en="Sample Z.P. School", name_mr="नमुना जिल्हा परिषद शाळा",
                            village="Sample Village", class_1_5_strength=120, class_6_8_strength=80)
            db.add(school); db.flush()
        if not db.scalar(select(AcademicYear).where(AcademicYear.code == "2026-27")):
            db.add(AcademicYear(code="2026-27", start_date=date(2026,4,1), end_date=date(2027,3,31), is_current=True))
        for key,en,mr in TRANSLATIONS:
            if not db.scalar(select(Translation).where(Translation.key == key)):
                db.add(Translation(key=key,text_en=en,text_mr=mr))
        for code,en,mr,wp,dow in MENUS:
            if not db.scalar(select(Menu).where(Menu.code == code)):
                db.add(Menu(code=code,name_en=en,name_mr=mr,week_pattern=wp,day_of_week=dow))
        for code,en,mr,cat,unit,track in INGREDIENTS:
            if not db.scalar(select(Ingredient).where(Ingredient.code == code)):
                db.add(Ingredient(code=code,name_en=en,name_mr=mr,category=cat,base_unit=unit,track_inventory=track))
        profile = db.scalar(select(SchoolProfile).where(SchoolProfile.school_id == school.id))
        if not profile:
            db.add(SchoolProfile(
                school_id=school.id,
                kitchen_type="SCHOOL_KITCHEN",
                headmaster_name="Demo Headmaster",
                meal_incharge_name="Demo Meal In-charge",
                created_by="seed",
            ))

        demo_access = [
            ("11111111-1111-1111-1111-111111111111", "teacher.demo", "TEACHER"),
            ("22222222-2222-2222-2222-222222222222", "headmaster.demo", "HEADMASTER"),
        ]
        for subject, username, role in demo_access:
            exists = db.scalar(select(UserSchoolAccess).where(
                UserSchoolAccess.keycloak_subject == subject,
                UserSchoolAccess.school_id == school.id,
                UserSchoolAccess.role == role,
            ))
            if not exists:
                db.add(UserSchoolAccess(
                    keycloak_subject=subject, username=username, school_id=school.id,
                    role=role, preferred_language="mr", active=True
                ))
        db.commit()
        print("Seed complete")
    finally:
        db.close()

if __name__ == "__main__":
    main()
