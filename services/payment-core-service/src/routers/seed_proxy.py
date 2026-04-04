"""
Seed Proxy Router — Generates realistic test data via existing REST API endpoints.

This ensures the full event-driven pipeline is triggered:
  API handler → Core DB write → Kafka publish → DB sync consumer → Read DB sync

Endpoints:
  POST /api/admin/seed — Generate seed data via API pipeline
  GET  /api/admin/seed/status — Check seed status (counts from Core DB)
"""
import asyncio
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/admin/seed", tags=["admin-seed"])

BASE_URL = "http://localhost:8001"
MAX_CONCURRENCY = 10
MAX_RETRIES = 3

INDIAN_FIRST_NAMES_MALE = [
    "Rahul", "Amit", "Vikram", "Arjun", "Rohan", "Karan", "Aditya", "Nikhil",
    "Suresh", "Rajesh", "Manoj", "Sanjay", "Pradeep", "Deepak", "Anil", "Sunil",
    "Pankaj", "Ravi", "Gaurav", "Sachin", "Vivek", "Ashish", "Mohit", "Ankit",
    "Sandeep", "Harish", "Naveen", "Kiran", "Tarun", "Varun", "Akash", "Siddharth",
    "Arvind", "Puneet", "Neeraj", "Himanshu", "Abhishek", "Shubham", "Yogesh", "Pranav",
]
INDIAN_FIRST_NAMES_FEMALE = [
    "Priya", "Sneha", "Anjali", "Pooja", "Neha", "Ritu", "Kavita", "Deepika",
    "Ritu", "Meena", "Sunita", "Rekha", "Asha", "Usha", "Lata", "Saroj",
    "Swati", "Nisha", "Rina", "Tina", "Pallavi", "Shruti", "Divya", "Shweta",
    "Megha", "Isha", "Aarti", "Simran", "Komal", "Jyoti", "Sakshi", "Riya",
    "Aditi", "Shraddha", "Tanvi", "Nidhi", "Vaishali", "Bhavna", "Kriti", "Ananya",
]
INDIAN_LAST_NAMES = [
    "Sharma", "Patel", "Kumar", "Singh", "Gupta", "Reddy", "Nair", "Iyer",
    "Joshi", "Desai", "Mehta", "Shah", "Verma", "Chopra", "Malhotra", "Kapoor",
    "Bhatia", "Saxena", "Agarwal", "Bansal", "Mishra", "Pandey", "Dubey", "Tiwari",
    "Srivastava", "Rao", "Pillai", "Menon", "Hegde", "Kulkarni", "Deshmukh", "Jadhav",
    "Patil", "Chavan", "Gaikwad", "More", "Pawar", "Shinde", "Jadhav", "Bhosale",
]

WESTERN_FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Paul", "Kimberly", "Andrew", "Emily", "Joshua", "Donna",
    "Kenneth", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory", "Debra",
    "Frank", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet", "Jack", "Catherine",
]
WESTERN_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Phillips", "Evans", "Turner", "Parker", "Collins", "Edwards",
    "Stewart", "Morris", "Murphy", "Cook", "Rogers", "Morgan", "Cooper", "Peterson",
    "Bailey", "Reed", "Kelly", "Howard", "Cox", "Ward", "Richardson", "Watson",
]

MERCHANT_CONFIG = {
    "TechStore Pro": {
        "category": "electronics",
        "descriptions": [
            "MacBook Pro 14-inch M3 Max", "Dell UltraSharp 27\" 4K Monitor",
            "Sony WH-1000XM5 Headphones", "iPad Air 256GB WiFi",
            "Logitech MX Master 3S Mouse", "Samsung 990 EVO 2TB SSD",
            "Adobe Creative Cloud Annual License", "Microsoft 365 Family Subscription",
            "Apple Magic Keyboard with Touch ID", "ASUS ROG Strix Gaming Monitor",
            "Razer BlackWidow V4 Mechanical Keyboard", "Anker 737 Power Bank 24000mAh",
            "Seagate Expansion 8TB External HDD", "TP-Link Archer AX73 Router",
            "NVIDIA Shield TV Pro Streaming", "Bose SoundLink Revolve+ Speaker",
        ],
        "metadata_templates": [
            lambda: {"product_sku": f"ELEC-{random.randint(10000, 99999)}", "warranty": random.choice(["1yr", "2yr", "3yr"]), "category": random.choice(["laptop", "monitor", "audio", "storage", "networking", "software"])},
            lambda: {"product_sku": f"ELEC-{random.randint(10000, 99999)}", "brand": random.choice(["Apple", "Dell", "Sony", "Samsung", "Logitech"]), "warranty": "extended"},
        ],
        "refund_reasons": [
            "Product defective on arrival", "Wrong model shipped",
            "Not compatible with existing setup", "Found better price elsewhere",
            "Performance not as advertised", "Packaging damaged during delivery",
        ],
        "currencies": ["USD", "EUR", "INR"],
        "currency_weights": [50, 30, 20],
    },
    "Fashion Hub": {
        "category": "fashion",
        "descriptions": [
            "Nike Air Max 90 — Size 10", "Levi's 501 Original Fit Jeans",
            "Ray-Ban Aviator Classic Sunglasses", "Adidas Ultraboost 23 Running Shoes",
            "Tommy Hilfiger Cotton Polo Shirt", "Zara Slim Fit Blazer Navy",
            "Gucci GG Marmont Leather Belt", "North Face Thermoball Eco Jacket",
            "Puma RS-X Sneakers White/Blue", "H&M Organic Cotton T-Shirt Pack",
            "Calvin Klein Boxer Briefs 3-Pack", "Fossil Gen 6 Smartwatch Rose Gold",
            "Vans Old Skool Classic Black/White", "Lacoste Classic Fit Pique Polo",
            "American Tourister Cabin Trolley Bag", "Michael Kors Jet Set Crossbody",
        ],
        "metadata_templates": [
            lambda: {"size": random.choice(["XS", "S", "M", "L", "XL", "XXL"]), "color": random.choice(["Black", "Navy", "White", "Grey", "Red", "Blue"]), "brand": random.choice(["Nike", "Adidas", "Levi's", "Ray-Ban", "Tommy Hilfiger", "Zara"])},
            lambda: {"size": random.choice(["6", "7", "8", "9", "10", "11"]), "color": random.choice(["Black", "White", "Brown"]), "material": random.choice(["Leather", "Canvas", "Synthetic"])},
        ],
        "refund_reasons": [
            "Size doesn't fit", "Color different from website",
            "Quality not as expected", "Received wrong item",
            "Fabric feels cheap", "Stitching came apart after first wash",
        ],
        "currencies": ["USD", "INR", "EUR"],
        "currency_weights": [40, 35, 25],
    },
    "Foodie Express": {
        "category": "food",
        "descriptions": [
            "Butter Chicken + Naan x2 + Raita", "Margherita Pizza (Large) + Garlic Bread",
            "Hyderabadi Biryani Combo Meal for 2", "Paneer Tikka Masala + Jeera Rice",
            "Chicken Shawarma Wrap + Fries + Coke", "Masala Dosa + Sambar + Coconut Chutney",
            "Veg Loaded Nachos + Cheese Dip", "Fish & Chips with Tartar Sauce",
            "Thai Green Curry + Jasmine Rice", "BBQ Chicken Wings (12pc) + Dips",
            "Mushroom Risotto + Garlic Breadsticks", "Chicken Teriyaki Bowl + Miso Soup",
            "Dal Makhani + Tandoori Roti x3", "Pasta Arrabiata + Caesar Salad",
            "Sushi Platter (16pc) + Edamame", "Tandoori Chicken Half + Mint Chutney",
        ],
        "metadata_templates": [
            lambda: {"restaurant": random.choice(["Spice Garden", "Pizza Palace", "Biryani House", "Wok This Way", "Tandoori Nights"]), "items": random.randint(1, 5), "delivery_fee": round(random.uniform(1.5, 4.5), 2)},
            lambda: {"restaurant": random.choice(["Dragon Wok", "The Burger Joint", "Taco Fiesta", "Sushi Master"]), "items": random.randint(2, 6), "delivery_time_min": random.randint(20, 55)},
        ],
        "refund_reasons": [
            "Order delivered cold", "Wrong items delivered",
            "Order never arrived", "Food quality was poor",
            "Missing items from order", "Allergy concern — contained undeclared ingredient",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [70, 30],
    },
    "TravelWise": {
        "category": "travel",
        "descriptions": [
            "Flight DEL→BOM — Economy Class", "Hotel Taj Mumbai — 2 Nights",
            "Travel Insurance Premium Annual", "Airport Transfer — Sedan AC",
            "Goa Beach Resort — 3 Nights All-Inclusive", "Train IRCTC — AC 2-Tier Sleeper",
            "Car Rental — Self-Drive Innova Crysta 3 Days", "Dubai Visa Processing — Express",
            "Maldives Honeymoon Package — 5 Nights", "Bus Volvo — Bangalore to Chennai Sleeper",
            "Cruise Mumbai-Goa-Mumbai — Balcony Cabin", "Adventure Sports Package — Rishikesh",
            "Kerala Houseboat — Alleppey 2 Nights", "Shimla-Manali Tour Package — 6 Days",
            "International Roaming Plan — 30 Days", "Lounge Access Pass — Priority Pass",
        ],
        "metadata_templates": [
            lambda: {"pnr": f"PNR{random.randint(100000, 999999)}", "departure": random.choice(["DEL", "BOM", "BLR", "MAA", "CCU"]), "arrival": random.choice(["BOM", "DEL", "GOI", "CCJ", "PNQ"]), "class": random.choice(["economy", "premium_economy", "business"])},
            lambda: {"booking_type": random.choice(["flight", "hotel", "package", "transfer", "insurance"]), "check_in": (datetime.now(timezone.utc) + timedelta(days=random.randint(7, 60))).strftime("%Y-%m-%d"), "guests": random.randint(1, 4)},
        ],
        "refund_reasons": [
            "Flight cancelled by airline", "Hotel overbooked",
            "Travel plans changed due to emergency", "Visa application rejected",
            "Weather conditions — trip cancelled", "Better deal found on competitor site",
        ],
        "currencies": ["INR", "USD", "EUR"],
        "currency_weights": [50, 30, 20],
    },
    "GameZone": {
        "category": "gaming",
        "descriptions": [
            "Steam Wallet ₹1000 Gift Card", "PlayStation Plus Annual Subscription",
            "Elden Ring — Digital Deluxe Edition", "Xbox Game Pass Ultimate — 12 Months",
            "Nintendo Switch Online Family Plan", "Call of Duty: Modern Warfare III",
            "FIFA 24 Ultimate Edition", "Razer Kraken V3 Pro Gaming Headset",
            "Logitech G Pro X Superlight Mouse", "SteelSeries Apex Pro TKL Keyboard",
            "Baldur's Gate 3 — Digital Copy", "PlayStation Store ₹2000 Wallet Top-Up",
            "GTA V Premium Online Edition", "Nintendo eShop ₹1500 Card",
            "HyperX Cloud III Wireless Headset", "NVIDIA GeForce NOW Priority — 6 Months",
        ],
        "metadata_templates": [
            lambda: {"platform": random.choice(["steam", "playstation", "xbox", "nintendo", "epic"]), "game_title": random.choice(["Elden Ring", "FIFA 24", "GTA V", "Baldur's Gate 3", "Call of Duty"]), "genre": random.choice(["action", "sports", "rpg", "fps", "adventure"])},
            lambda: {"platform": random.choice(["steam", "playstation", "xbox"]), "item_type": random.choice(["subscription", "wallet_topup", "game", "accessory"]), "region": random.choice(["IN", "US", "EU"])},
        ],
        "refund_reasons": [
            "Game doesn't run on my system", "Accidental purchase",
            "Game not as described", "Subscription auto-renewed — didn't want it",
            "Found game cheaper during sale", "Content too violent for intended user",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [60, 40],
    },
    "BookWorm Digital": {
        "category": "books",
        "descriptions": [
            "Atomic Habits — James Clear (Hardcover)", "The Psychology of Money — Morgan Housel",
            "Deep Work — Cal Newport (Paperback)", "Kindle Paperwhite 2024 Edition",
            "Sapiens — Yuval Noah Harari (Audiobook)", "Project Hail Mary — Andy Weir",
            "The Alchemist — Paulo Coelho (Special Edition)", "Blinkist Premium Annual Subscription",
            "Audible Plus Membership — 12 Months", "Dune — Frank Herbert (Illustrated)",
            "The Art of War — Sun Tzu (Leather Bound)", "Thinking Fast and Slow — Daniel Kahneman",
            "Rich Dad Poor Dad — Robert Kiyosaki", "The Lean Startup — Eric Ries",
            "Good to Great — Jim Collins", "Zero to One — Peter Thiel",
        ],
        "metadata_templates": [
            lambda: {"format": random.choice(["hardcover", "paperback", "ebook", "audiobook"]), "isbn": f"978-{random.randint(1000000000, 9999999999)}", "pages": random.randint(150, 600)},
            lambda: {"format": random.choice(["ebook", "audiobook"]), "narrator": random.choice(["Audible Studios", "Penguin Audio", "HarperAudio"]), "duration_hours": random.randint(3, 20)},
        ],
        "refund_reasons": [
            "Book arrived damaged", "Wrong edition received",
            "Audiobook quality is poor", "Ebook DRM issues",
            "Content not as described", "Already purchased on another platform",
        ],
        "currencies": ["USD", "INR", "EUR"],
        "currency_weights": [40, 35, 25],
    },
    "HealthFirst": {
        "category": "health",
        "descriptions": [
            "Annual Health Checkup — Premium Package", "Telemedicine Consultation — General",
            "Prescription Refill — 3 Months Supply", "Dental Cleaning & Checkup",
            "Eye Examination + Contact Lenses", "Physiotherapy Session — 60 min",
            "Mental Health Counseling — 1 Hour", "Vitamin D3 + K2 Supplement (90 caps)",
            "Fitbit Charge 6 Fitness Tracker", "Organic Protein Powder — 2kg",
            "First Aid Kit — Complete 200pc", "Blood Pressure Monitor — Digital",
            "Yoga Mat Premium — 6mm", "Meditation App — Annual Premium",
            "COVID-19 Rapid Antigen Test Kit (5pc)", "Allergy Test Panel — Comprehensive",
        ],
        "metadata_templates": [
            lambda: {"service_type": random.choice(["consultation", "lab_test", "pharmacy", "equipment"]), "doctor": random.choice(["Dr. Sharma", "Dr. Patel", "Dr. Reddy"]), "specialty": random.choice(["general", "cardiology", "orthopedics", "dermatology"])},
            lambda: {"product_type": random.choice(["supplement", "equipment", "test_kit"]), "prescription_required": random.choice([True, False]), "insurance_claim": random.choice([True, False])},
        ],
        "refund_reasons": [
            "Appointment cancelled by doctor", "Lab results delayed beyond SLA",
            "Medication caused adverse reaction", "Equipment malfunction on arrival",
            "Insurance claim rejected", "Service not available at booked slot",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [65, 35],
    },
    "AutoParts Direct": {
        "category": "automotive",
        "descriptions": [
            "Bosch Brake Pad Set — Front", "Michelin Pilot Sport 4 — 205/55R16",
            "Castrol EDGE 5W-30 Synthetic Oil 5L", "K&N Performance Air Filter",
            "NGK Iridium Spark Plugs (Set of 4)", "Brembo Brake Disc — Ventilated 300mm",
            "Exide Car Battery — 12V 60Ah", "Philips XeonVision LED Headlight H7",
            "Mann-Filter Oil Filter — W 712/95", "Continental ContiPremiumContact 5",
            "Bosch Windshield Wiper Set — 26/16", "Denso AC Compressor — Universal",
            "Shell Helix Ultra 0W-20 — 4L", "Valeo Clutch Kit — Complete Set",
            "Febi Bilstein Suspension Strut", "Mahle Fuel Filter — Diesel",
        ],
        "metadata_templates": [
            lambda: {"part_type": random.choice(["brake", "engine", "suspension", "electrical", "filter"]), "vehicle_make": random.choice(["Maruti", "Hyundai", "Toyota", "Honda", "Tata"]), "oem_number": f"OEM-{random.randint(100000, 999999)}"},
            lambda: {"part_type": random.choice(["tire", "battery", "oil", "lighting"]), "warranty_months": random.choice([6, 12, 24, 36]), "compatibility": random.choice(["universal", "model-specific"])},
        ],
        "refund_reasons": [
            "Part doesn't fit my vehicle", "Received wrong part number",
            "Part arrived damaged", "Quality below OEM standard",
            "Found cheaper at local dealer", "Vehicle sold — no longer needed",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [70, 30],
    },
    "PetPalace": {
        "category": "pets",
        "descriptions": [
            "Royal Canin Adult Dog Food — 15kg", "Cat Litter Box — Self-Cleaning",
            "Dog Grooming Kit — Professional 7pc", "Aquarium Filter — 500L/hr",
            "Bird Cage — Large Stainless Steel", "Pet GPS Tracker Collar",
            "Catnip Toys Set — 20 Pieces", "Dog Bed — Orthopedic Memory Foam",
            "Fish Food Flakes — Premium 500g", "Pet Insurance — Annual Plan",
            "Dog Leash — Retractable 5m", "Cat Scratching Post — 120cm Tower",
            "Hamster Wheel — Silent Spinner", "Pet Shampoo — Oatmeal & Aloe 500ml",
            "Dog Training Treats — Chicken 1kg", "Automatic Pet Feeder — WiFi Enabled",
        ],
        "metadata_templates": [
            lambda: {"pet_type": random.choice(["dog", "cat", "fish", "bird", "hamster"]), "product_type": random.choice(["food", "toy", "accessory", "health", "furniture"]), "pet_size": random.choice(["small", "medium", "large"])},
            lambda: {"pet_type": random.choice(["dog", "cat"]), "age_range": random.choice(["puppy", "adult", "senior"]), "breed_specific": random.choice([True, False])},
        ],
        "refund_reasons": [
            "Pet doesn't like the food", "Product size incorrect",
            "Toy broke within a day", "Allergic reaction to product",
            "Item arrived expired", "Wrong product delivered",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [60, 40],
    },
    "HomeDecor Plus": {
        "category": "home",
        "descriptions": [
            "IKEA KALLAX Shelf Unit — White", "Philips Hue Smart Bulb Starter Kit",
            "Memory Foam Pillow — Cervical Support", "Dyson V15 Detect Cordless Vacuum",
            "KitchenAid Stand Mixer — Artisan", "Egyptian Cotton Bedsheet — King Size",
            "Wall Art Canvas — Abstract 3pc Set", "Instant Pot Duo 7-in-1 — 6 Quart",
            "Bamboo Cutting Board Set — 3pc", "Smart Thermostat — Nest Learning",
            "Blackout Curtains — 2 Panel Set", "Scented Candle Set — Soy Wax 6pc",
            "Robot Vacuum — iRobot Roomba", "Ceramic Plant Pot Set — Modern 4pc",
            "LED Strip Lights — 10m RGB WiFi", "Weighted Blanket — 7kg Queen",
        ],
        "metadata_templates": [
            lambda: {"room": random.choice(["living", "bedroom", "kitchen", "bathroom", "office"]), "style": random.choice(["modern", "minimalist", "bohemian", "industrial", "scandinavian"]), "material": random.choice(["wood", "metal", "ceramic", "fabric", "glass"])},
            lambda: {"room": random.choice(["living", "bedroom", "kitchen"]), "color": random.choice(["white", "black", "grey", "natural", "navy"]), "assembly_required": random.choice([True, False])},
        ],
        "refund_reasons": [
            "Color different from photos", "Dimensions not as listed",
            "Product arrived broken", "Quality below expectations",
            "Doesn't match existing decor", "Assembly instructions unclear",
        ],
        "currencies": ["USD", "INR", "EUR"],
        "currency_weights": [40, 30, 30],
    },
    "FitLife Gym": {
        "category": "fitness",
        "descriptions": [
            "Annual Gym Membership — Premium", "Personal Training — 10 Sessions",
            "Yoga Class — Monthly Unlimited", "CrossFit Drop-In — Single Session",
            "Nutrition Consultation — 1 Hour", "Group Zumba Class — 1 Month",
            "Swimming Pool Access — Quarterly", "Body Composition Analysis — DEXA",
            "Home Workout Equipment Kit", "Protein Bar Box — 24pc Assorted",
            "Resistance Bands Set — 5 Levels", "Foam Roller — High Density",
            "Gym Bag — Duffel 40L", "Fitness Tracker — Annual Premium App",
            "Sauna Session — 10 Pack", "Sports Massage — 60 min",
        ],
        "metadata_templates": [
            lambda: {"membership_type": random.choice(["basic", "premium", "vip"]), "duration": random.choice(["monthly", "quarterly", "annual"]), "trainer": random.choice(["Coach Raj", "Trainer Priya", "Coach Amit"])},
            lambda: {"service_type": random.choice(["class", "personal_training", "equipment", "supplement"]), "intensity": random.choice(["beginner", "intermediate", "advanced"])},
        ],
        "refund_reasons": [
            "Gym closed during advertised hours", "Trainer unavailable for booked slots",
            "Equipment under maintenance too long", "Relocated — no branch nearby",
            "Medical reason — can't exercise", "Found better facility elsewhere",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [65, 35],
    },
    "CloudNine SaaS": {
        "category": "saas",
        "descriptions": [
            "Cloud Hosting — Business Plan Monthly", "CRM License — 10 Users Annual",
            "Email Marketing — 50K Contacts Plan", "Project Management — Team 25 Users",
            "SSL Certificate — Wildcard Annual", "CDN Bandwidth — 1TB Overage",
            "API Gateway — Enterprise Tier", "Database Backup — 500GB Monthly",
            "Monitoring Dashboard — Pro Plan", "CI/CD Pipeline — Unlimited Builds",
            "Team Chat — Business Annual", "Video Conferencing — 100 Participants",
            "Document Signing — 500 Docs/Month", "Password Manager — Enterprise 50 Seats",
            "Analytics Platform — Growth Tier", "DevOps Suite — Annual License",
        ],
        "metadata_templates": [
            lambda: {"plan_type": random.choice(["starter", "business", "enterprise"]), "billing_cycle": random.choice(["monthly", "annual"]), "seats": random.choice([5, 10, 25, 50, 100])},
            lambda: {"service": random.choice(["hosting", "crm", "analytics", "security"]), "region": random.choice(["us-east", "eu-west", "ap-south"]), "sla_tier": random.choice(["standard", "premium", "critical"])},
        ],
        "refund_reasons": [
            "Service downtime exceeded SLA", "Features not as advertised",
            "Migrating to competitor", "Company downsizing — reducing seats",
            "Billing error — double charged", "Trial ended — accidental charge",
        ],
        "currencies": ["USD", "EUR", "INR"],
        "currency_weights": [50, 30, 20],
    },
    "QuickShip Logistics": {
        "category": "logistics",
        "descriptions": [
            "Express Delivery — Mumbai to Delhi", "International Freight — 20ft Container",
            "Warehousing — 500 sqft Monthly", "Last Mile Delivery — 100 Parcels",
            "Cold Chain Transport — Pharma Grade", "Customs Clearance — Import License",
            "Package Insurance — ₹50K Coverage", "Bulk Shipment — 500kg Air Freight",
            "Return Management — Reverse Logistics", "Tracking API — Enterprise Access",
            "Pallet Shipping — 4 Pallets", "Document Courier — Same Day",
            "Fulfillment Center — Pick & Pack 200 orders", "Cross-Border E-commerce Shipping",
            "Heavy Machinery Transport — Oversized", "Temperature Monitoring — IoT Sensors",
        ],
        "metadata_templates": [
            lambda: {"service_type": random.choice(["express", "freight", "warehousing", "last_mile"]), "origin": random.choice(["Mumbai", "Delhi", "Bangalore", "Chennai"]), "destination": random.choice(["Delhi", "Kolkata", "Hyderabad", "Pune"])},
            lambda: {"weight_kg": random.randint(1, 500), "dimensions_cm": f"{random.randint(20, 200)}x{random.randint(20, 150)}x{random.randint(20, 100)}", "priority": random.choice(["standard", "express", "same_day"])},
        ],
        "refund_reasons": [
            "Delivery delayed beyond承诺 date", "Package damaged in transit",
            "Wrong delivery address", "Customs clearance failed",
            "Service not available in area", "Tracking system malfunction",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [70, 30],
    },
    "GreenLeaf Organics": {
        "category": "organic",
        "descriptions": [
            "Organic Honey — Raw 500ml", "Cold-Pressed Coconut Oil — 1L",
            "Quinoa — Organic 1kg", "Matcha Green Tea Powder — Ceremonial 100g",
            "Organic Almond Butter — 350g", "Chia Seeds — Premium Grade 500g",
            "Turmeric Powder — Organic 200g", "Organic Dark Chocolate 85% — 100g",
            "Apple Cider Vinegar — With Mother 750ml", "Organic Basmati Rice — 5kg",
            "Spirulina Tablets — 500mg 200pc", "Organic Ghee — A2 Cow 1L",
            "Mixed Nuts Trail Mix — 1kg", "Organic Green Coffee Beans 500g",
            "Flaxseed Oil — Cold Pressed 250ml", "Organic Maple Syrup — Grade A 375ml",
        ],
        "metadata_templates": [
            lambda: {"certification": random.choice(["USDA Organic", "India Organic", "EU Organic"]), "origin": random.choice(["India", "Sri Lanka", "Thailand", "New Zealand"]), "shelf_life_months": random.choice([6, 12, 18, 24])},
            lambda: {"product_type": random.choice(["superfood", "oil", "grain", "snack", "beverage"]), "vegan": random.choice([True, True, False]), "gluten_free": random.choice([True, True, False])},
        ],
        "refund_reasons": [
            "Product past expiry date", "Packaging seal was broken",
            "Taste/quality inconsistent", "Not actually organic certified",
            "Allergic reaction — undeclared allergen", "Delivery took too long — product spoiled",
        ],
        "currencies": ["INR", "USD", "EUR"],
        "currency_weights": [50, 30, 20],
    },
    "SmartHome IoT": {
        "category": "iot",
        "descriptions": [
            "Smart Door Lock — Fingerprint + WiFi", "Ring Video Doorbell — Pro 2",
            "Smart Thermostat — Learning WiFi", "Philips Hue Play Light Bar — 2pc",
            "Smart Plug — Energy Monitoring 4-Pack", "Security Camera — 4K Outdoor 2pc",
            "Smart Blinds Motor — WiFi Enabled", "Water Leak Sensor — 3 Pack",
            "Smart Smoke Detector — WiFi", "Robot Mop — Braava Jet m6",
            "Smart Garage Door Opener", "Zigbee Hub — Matter Compatible",
            "Smart Irrigation Controller — 8 Zone", "Air Quality Monitor — PM2.5 + CO2",
            "Smart Mirror — Bathroom Anti-Fog", "Voice Assistant — Smart Display 10\"",
        ],
        "metadata_templates": [
            lambda: {"protocol": random.choice(["WiFi", "Zigbee", "Z-Wave", "Matter", "Bluetooth"]), "compatibility": random.choice(["Alexa", "Google Home", "HomeKit", "All"]), "power": random.choice(["battery", "wired", "solar"])},
            lambda: {"room": random.choice(["living", "bedroom", "kitchen", "garage", "outdoor"]), "smart_features": random.choice(["voice_control", "automation", "remote_access", "energy_monitoring"])},
        ],
        "refund_reasons": [
            "Device won't connect to WiFi", "Not compatible with existing hub",
            "App is buggy and unreliable", "False alarms from sensors",
            "Device stopped working after update", "Privacy concerns with camera",
        ],
        "currencies": ["USD", "INR", "EUR"],
        "currency_weights": [40, 35, 25],
    },
    "Artisan Crafts": {
        "category": "crafts",
        "descriptions": [
            "Hand-Painted Ceramic Vase — Blue", "Macrame Wall Hanging — Large",
            "Handwoven Silk Scarf — Paisley", "Wooden Jewelry Box — Carved Teak",
            "Handmade Soap Set — Lavender 4pc", "Pottery Bowl — Stoneware Glazed",
            "Leather Journal — Handbound A5", "Silver Earrings — Handcrafted Tribal",
            "Embroidered Cushion Cover — 2pc", "Candle Making Kit — Soy Wax Complete",
            "Hand-Knitted Wool Blanket — Queen", "Glass Painting Kit — 6 Colors",
            "Resin Art Coaster Set — 4pc Ocean", "Handmade Paper — Cotton Rag 50 Sheets",
            "Crochet Hook Set — Bamboo 8pc", "Watercolor Paint Set — Professional 24",
        ],
        "metadata_templates": [
            lambda: {"craft_type": random.choice(["pottery", "textile", "woodwork", "jewelry", "painting"]), "handmade": True, "customizable": random.choice([True, False]), "artist": random.choice(["Meera", "Ravi", "Lakshmi", "Arjun"])},
            lambda: {"material": random.choice(["cotton", "silk", "wood", "clay", "silver", "glass"]), "style": random.choice(["traditional", "contemporary", "fusion", "minimalist"])},
        ],
        "refund_reasons": [
            "Product different from listing photos", "Handmade variation too significant",
            "Item arrived broken", "Color faded after first use",
            "Gift recipient already has one", "Quality of craftsmanship below expectation",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [55, 45],
    },
    "MediCare Pharmacy": {
        "category": "pharmacy",
        "descriptions": [
            "Prescription — Monthly Refill (5 meds)", "OTC Pain Relief — Ibuprofen 200mg",
            "Blood Glucose Test Strips — 50pc", "Digital Thermometer — Infrared",
            "First Aid Bandages — Assorted 100pc", "Multivitamin — Daily Complete 90pc",
            "Hand Sanitizer — 500ml Pump", "Face Masks — N95 (Pack of 10)",
            "Eye Drops — Lubricant 15ml", "Cough Syrup — Sugar-Free 200ml",
            "Sunscreen SPF 50+ — 100ml", "Wound Care Kit — Complete",
            "Pulse Oximeter — Fingertip", "Nebulizer Machine — Portable",
            "Calcium + Vitamin D3 — 120 Tablets", "Probiotic Capsules — 30pc",
        ],
        "metadata_templates": [
            lambda: {"prescription_required": random.choice([True, False]), "generic_available": random.choice([True, False]), "insurance_covered": random.choice([True, False])},
            lambda: {"category": random.choice(["prescription", "otc", "wellness", "device", "supplement"]), "dosage_form": random.choice(["tablet", "capsule", "syrup", "cream", "drops"])},
        ],
        "refund_reasons": [
            "Prescription cancelled by doctor", "Wrong medication dispensed",
            "Expired product delivered", "Packaging tampered",
            "Adverse side effects", "Found generic alternative cheaper",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [70, 30],
    },
    "EduLearn Academy": {
        "category": "education",
        "descriptions": [
            "Python Programming — Complete Course", "IELTS Preparation — Online Bundle",
            "Data Science Bootcamp — 6 Months", "Graphic Design — Adobe Masterclass",
            "Digital Marketing Certification", "Machine Learning — Advanced Track",
            "Business English — Corporate Training", "Web Development — Full Stack MERN",
            "Financial Modeling — Excel Advanced", "Photography — Beginner to Pro",
            "Music Production — Ableton Live Course", "Public Speaking — Confidence Builder",
            "AWS Solutions Architect — Prep Course", "UI/UX Design — Figma Masterclass",
            "Blockchain Development — Solidity", "Project Management — PMP Prep",
        ],
        "metadata_templates": [
            lambda: {"course_type": random.choice(["video", "live", "hybrid"]), "duration_hours": random.randint(10, 200), "level": random.choice(["beginner", "intermediate", "advanced"]), "certificate": random.choice([True, True, False])},
            lambda: {"instructor": random.choice(["Prof. Sharma", "Dr. Gupta", "Coach Patel"]), "language": random.choice(["English", "Hindi", "Bilingual"]), "access_duration": random.choice(["lifetime", "1_year", "6_months"])},
        ],
        "refund_reasons": [
            "Course content outdated", "Instructor quality below expectation",
            "Technical issues with platform", "Course not as described",
            "Completed course — accidental re-purchase", "Found free alternative on YouTube",
        ],
        "currencies": ["INR", "USD"],
        "currency_weights": [60, 40],
    },
    "StreamVibe Entertainment": {
        "category": "entertainment",
        "descriptions": [
            "Streaming Subscription — Annual Premium", "Movie Tickets — IMAX 2pc",
            "Concert Tickets — Front Row", "Gaming Pass — Monthly Ultimate",
            "E-Book Unlimited — Annual Plan", "Music Streaming — Hi-Fi Family",
            "Podcast Premium — Ad-Free Annual", "Sports Package — Live Cricket Annual",
            "VR Experience — 10 Session Pack", "Comedy Show — Stand-Up Live",
            "Documentary Collection — Nature 4K", "Anime Subscription — Premium Monthly",
            "Audiobook Credits — 12 Monthly", "Theater Play — VIP Seats 2pc",
            "Karaoke Machine — Home System", "Board Game Collection — 10 Classics",
        ],
        "metadata_templates": [
            lambda: {"content_type": random.choice(["movie", "series", "music", "game", "live_event"]), "quality": random.choice(["HD", "4K", "Dolby Atmos", "Standard"]), "genre": random.choice(["action", "comedy", "drama", "documentary", "horror"])},
            lambda: {"platform": random.choice(["StreamVibe", "Partner Network"]), "device_limit": random.choice([1, 2, 4, 6]), "offline_download": random.choice([True, False])},
        ],
        "refund_reasons": [
            "Content library smaller than expected", "Streaming quality issues",
            "Event cancelled/postponed", "Subscription auto-renewed accidentally",
            "Better deal on competitor platform", "Account sharing restriction too strict",
        ],
        "currencies": ["INR", "USD", "EUR"],
        "currency_weights": [50, 30, 20],
    },
    "CryptoVault Exchange": {
        "category": "crypto",
        "descriptions": [
            "BTC Purchase — 0.01 BTC", "ETH Staking — Annual Yield Plan",
            "USDT Deposit — $1000 Equivalent", "Trading Fee — Pro Tier Monthly",
            "NFT Minting — Collection Drop", "DeFi Yield Farm — 90 Day Lock",
            "Crypto Tax Report — Annual", "Hardware Wallet — Ledger Nano X",
            "Premium API Access — Monthly", "Margin Trading — Interest 30 Days",
            "SOL Purchase — 10 SOL", "Portfolio Management — Advisory Monthly",
            "Crypto Insurance — Annual Coverage", "OTC Desk — Large Block Trade Fee",
            "Mining Pool — Monthly Membership", "Token Launch — Early Access Pass",
        ],
        "metadata_templates": [
            lambda: {"asset": random.choice(["BTC", "ETH", "SOL", "USDT", "MATIC", "ADA"]), "transaction_type": random.choice(["buy", "sell", "stake", "swap", "deposit"]), "network": random.choice(["Ethereum", "Solana", "Polygon", "Bitcoin"])},
            lambda: {"risk_level": random.choice(["low", "medium", "high"]), "lock_period_days": random.choice([0, 30, 90, 180, 365]), "apy_percent": round(random.uniform(2.0, 15.0), 1)},
        ],
        "refund_reasons": [
            "Transaction failed on blockchain", "Exchange downtime during critical trade",
            "Unauthorized access to account", "Withdrawal delayed beyond SLA",
            "Hidden fees not disclosed", "Regulatory concern in jurisdiction",
        ],
        "currencies": ["USD", "INR"],
        "currency_weights": [60, 40],
    },
}

MERCHANT_NAME_POOL = [
    "TechStore Pro", "Fashion Hub", "Foodie Express", "TravelWise", "GameZone",
    "BookWorm Digital", "HealthFirst", "AutoParts Direct", "PetPalace", "HomeDecor Plus",
    "FitLife Gym", "CloudNine SaaS", "QuickShip Logistics", "GreenLeaf Organics",
    "SmartHome IoT", "Artisan Crafts", "MediCare Pharmacy", "EduLearn Academy",
    "StreamVibe Entertainment", "CryptoVault Exchange",
]

GENERIC_CONFIG = {
    "descriptions": [
        "Order #{order_id} — Premium Subscription",
        "Order #{order_id} — Product Purchase",
        "Order #{order_id} — Service Fee",
        "Order #{order_id} — Monthly Plan",
        "Order #{order_id} — Annual Renewal",
        "Order #{order_id} — One-time Purchase",
        "Order #{order_id} — Upgrade Fee",
        "Order #{order_id} — Add-on Package",
    ],
    "metadata_templates": [
        lambda: {"order_ref": f"ORD-{random.randint(10000, 99999)}"},
    ],
    "refund_reasons": [
        "Customer requested refund", "Product not as described", "Duplicate charge",
        "Fraudulent transaction", "Service not delivered", "Customer changed mind",
    ],
    "currencies": ["USD", "EUR", "INR"],
    "currency_weights": [40, 30, 30],
}

DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "protonmail.com", "company.com", "mail.com", "rediffmail.com", "aol.com"]

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
METHOD_WEIGHTS = [45, 25, 20, 10]

UPI_BANKS = ["SBI", "HDFC", "ICICI", "Axis", "Kotak", "BOB", "PNB", "Yes Bank", "IDFC First"]
UPI_APPS = ["paytm", "oksbi", "okhdfcbank", "okaxis", "ybl", "ibl", "upi"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

DEVICES = ["desktop", "mobile", "tablet"]
DEVICE_WEIGHTS = [50, 35, 15]

INDIAN_IP_RANGES = [
    "103.{}.{}.{}", "49.{}.{}.{}", "117.{}.{}.{}", "122.{}.{}.{}",
    "182.{}.{}.{}", "223.{}.{}.{}", "157.{}.{}.{}", "106.{}.{}.{}",
]


def _random_email(first, last, use_indian=True):
    domain = random.choice(DOMAINS)
    num = random.randint(1, 999)
    if use_indian and random.random() < 0.6:
        return random.choice([
            f"{first.lower()}.{last.lower()}{num}@{domain}",
            f"{first.lower()}{num}@{domain}",
            f"{first[0].lower()}{last.lower()}{num}@{domain}",
        ])
    return random.choice([
        f"{first.lower()}.{last.lower()}{num}@{domain}",
        f"{first.lower()}{last[0].lower()}{num}@{domain}",
    ])


def _random_phone(use_indian=True):
    if use_indian and random.random() < 0.7:
        return f"+91{random.randint(6000000000, 9999999999)}"
    return f"+1{random.randint(2000000000, 9999999999)}"


def _random_upi_id(first, last):
    bank = random.choice(UPI_APPS)
    return f"{first.lower()}.{last.lower()}{random.randint(1, 999)}@{bank}"


def _random_amount(min_val=5.0, max_val=5000.0):
    return round(random.uniform(min_val, max_val), 2)


def _pick_weighted(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def _random_ip():
    template = random.choice(INDIAN_IP_RANGES)
    return template.format(random.randint(0, 255), random.randint(0, 255), random.randint(1, 254))


def _random_date_ist(days_back=90):
    now = datetime.now(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    ist_now = now + ist_offset

    hour_weights = [1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 12, 12, 10, 10, 8, 8, 6, 6, 5, 4, 3, 2, 1, 1]
    hour = random.choices(range(24), weights=hour_weights, k=1)[0]

    is_weekend = random.random() < 0.25
    if is_weekend:
        day_offset = random.choice([5, 6])
    else:
        day_offset = random.choices(range(5), weights=[1, 1, 1, 1, 1], k=1)[0]

    recent_weight = random.random()
    if recent_weight < 0.6:
        days_offset = random.randint(0, 30)
    elif recent_weight < 0.85:
        days_offset = random.randint(31, 60)
    else:
        days_offset = random.randint(61, days_back)

    target_ist = ist_now - timedelta(days=days_offset)
    target_ist = target_ist.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59))
    target_utc = target_ist - ist_offset
    return target_utc.isoformat()


def _get_merchant_config(merchant_name):
    return MERCHANT_CONFIG.get(merchant_name, GENERIC_CONFIG)


def _generate_payment_description(merchant_name):
    config = _get_merchant_config(merchant_name)
    desc = random.choice(config["descriptions"])
    if "{order_id}" in desc:
        desc = desc.format(order_id=random.randint(10000, 99999))
    return desc


def _generate_payment_metadata(merchant_name, method):
    config = _get_merchant_config(merchant_name)
    meta_template = random.choice(config["metadata_templates"])
    metadata = meta_template()

    metadata["order_id"] = f"ORD-{datetime.now(timezone.utc).strftime('%Y')}-{random.randint(10000, 99999)}"
    metadata["ip_address"] = _random_ip()
    metadata["user_agent"] = random.choice(USER_AGENTS)
    metadata["device"] = _pick_weighted(DEVICES, DEVICE_WEIGHTS)

    if method == "upi":
        first = random.choice(INDIAN_FIRST_NAMES_MALE + INDIAN_FIRST_NAMES_FEMALE)
        last = random.choice(INDIAN_LAST_NAMES)
        metadata["upi_id"] = _random_upi_id(first, last)
        metadata["bank"] = random.choice(UPI_BANKS)
    elif method == "wallet":
        metadata["wallet_provider"] = random.choice(["Paytm", "PhonePe", "Amazon Pay", "MobiKwik", "FreeCharge"])
    elif method == "netbanking":
        metadata["bank"] = random.choice(UPI_BANKS)
        metadata["ifsc_prefix"] = random.choice(["SBIN", "HDFC", "ICIC", "UTIB", "KKBK"])

    return metadata


def _generate_refund_reason(merchant_name):
    config = _get_merchant_config(merchant_name)
    return random.choice(config["refund_reasons"])


async def _retry_request(func, *args, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await func(*args, **kwargs)
            if resp.status_code in (200, 201, 204):
                return resp
            if attempt == MAX_RETRIES:
                return resp
        except Exception:
            if attempt == MAX_RETRIES:
                raise
        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
    return None


MIN_MERCHANTS = 10
MIN_CUSTOMERS_PER_MERCHANT = 1000
MIN_PAYMENTS_PER_MERCHANT = 1000
MAX_SEED_DURATION = 300  # 5 minutes


async def _generate_seed_data(num_merchants: int = 20):
    start_time = time.time()
    results = {
        "merchants_created": 0, "customers_created": 0, "payments_created": 0,
        "payments_authorized": 0, "payments_captured": 0, "payments_settled": 0,
        "payments_failed": 0, "refunds_created": 0, "refunds_processed": 0,
        "partial_refunds": 0, "full_refunds": 0, "failed_api_calls": 0,
        "retried_successfully": 0, "skipped_merchants": 0, "skipped_customers": 0,
        "skipped_payments": 0, "timed_out": False,
    }

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    def _check_timeout():
        if time.time() - start_time > MAX_SEED_DURATION:
            results["timed_out"] = True
            return True
        return False

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ─── Step 1: Get existing merchants ────────────────────────────
        existing_resp = await _retry_request(client.get, f"{BASE_URL}/api/merchants")
        existing_merchants = existing_resp.json().get("data", []) if existing_resp else []
        existing_names = {m["name"] for m in existing_merchants}

        # If we already have enough merchants, skip creation entirely
        if len(existing_merchants) >= MIN_MERCHANTS:
            merchants = []
            for m in existing_merchants:
                # Only use merchants that are in our known pool
                if m["name"] in MERCHANT_NAME_POOL:
                    m["_config_name"] = m["name"]
                    merchants.append(m)
            # If pool merchants < MIN_MERCHANTS, use all existing
            if len(merchants) < MIN_MERCHANTS:
                merchants = existing_merchants[:num_merchants]
                for m in merchants:
                    m["_config_name"] = m["name"]
            results["skipped_merchants"] = len(merchants)
        else:
            merchants = []
            for i in range(num_merchants):
                name = MERCHANT_NAME_POOL[i % len(MERCHANT_NAME_POOL)]
                if name in existing_names:
                    merchant = next(m for m in existing_merchants if m["name"] == name)
                else:
                    email = f"contact-{i+1}-{uuid.uuid4().hex[:6]}@{name.lower().replace(' ', '')}.com"
                    resp = await _retry_request(
                        client.post, f"{BASE_URL}/api/merchants",
                        json={"name": name, "email": email, "status": "active"},
                    )
                    if resp is None or resp.status_code not in (200, 201):
                        raise HTTPException(status_code=500, detail=f"Failed to create merchant {name}")
                    merchant = resp.json()
                    results["merchants_created"] += 1
                    existing_merchants.append(merchant)
                    existing_names.add(name)

                merchant["_config_name"] = name
                merchants.append(merchant)

        # ─── Step 2: Customers per merchant (skip if already enough) ───
        customers_by_merchant = {}

        async def _create_customer(m, first, last, email, phone):
            async with semaphore:
                resp = await _retry_request(
                    client.post, f"{BASE_URL}/api/{m['merchant_id']}/customers",
                    json={"name": f"{first} {last}", "email": email, "phone": phone},
                    headers={"X-API-Key": m["api_key"]},
                )
                if resp and resp.status_code in (200, 201):
                    return resp.json()
                results["failed_api_calls"] += 1
                return None

        for m in merchants:
            if _check_timeout():
                break
            mid = m["merchant_id"]

            # Check existing customer count
            cust_resp = await _retry_request(
                client.get, f"{BASE_URL}/api/{mid}/customers",
                headers={"X-API-Key": m["api_key"]},
            )
            existing_cust_count = 0
            existing_custs = []
            if cust_resp and cust_resp.status_code in (200, 201):
                cust_data = cust_resp.json()
                if isinstance(cust_data, dict):
                    existing_cust_count = cust_data.get("total", 0)
                    existing_custs = cust_data.get("data", [])
                elif isinstance(cust_data, list):
                    existing_cust_count = len(cust_data)
                    existing_custs = cust_data

            customers_by_merchant[mid] = existing_custs

            if existing_cust_count >= MIN_CUSTOMERS_PER_MERCHANT:
                results["skipped_customers"] += existing_cust_count
                continue

            need = random.randint(100, 300)
            use_indian = random.random() < 0.6

            tasks = []
            for _ in range(need):
                if use_indian:
                    is_male = random.random() < 0.5
                    first = random.choice(INDIAN_FIRST_NAMES_MALE if is_male else INDIAN_FIRST_NAMES_FEMALE)
                    last = random.choice(INDIAN_LAST_NAMES)
                else:
                    first = random.choice(WESTERN_FIRST_NAMES)
                    last = random.choice(WESTERN_LAST_NAMES)
                email = _random_email(first, last, use_indian)
                phone = _random_phone(use_indian)
                tasks.append(_create_customer(m, first, last, email, phone))

            created = await asyncio.gather(*tasks)
            for cust in created:
                if cust:
                    customers_by_merchant[mid].append(cust)
                    results["customers_created"] += 1

        # ─── Step 3: Payments per merchant (skip if already enough) ────
        payments_by_merchant = {}

        async def _create_payment(m, cust):
            async with semaphore:
                amount = _random_amount(10.0, 2500.0)
                config = _get_merchant_config(m["_config_name"])
                currency = _pick_weighted(config["currencies"], config["currency_weights"])
                method = _pick_weighted(PAYMENT_METHODS, METHOD_WEIGHTS)
                desc = _generate_payment_description(m["_config_name"])
                metadata = _generate_payment_metadata(m["_config_name"], method)

                resp = await _retry_request(
                    client.post, f"{BASE_URL}/api/{m['merchant_id']}/payments",
                    json={
                        "customer_id": cust["customer_id"], "amount": amount,
                        "currency": currency, "method": method,
                        "description": desc, "metadata": metadata,
                    },
                    headers={"X-API-Key": m["api_key"]},
                )
                if resp and resp.status_code in (200, 201):
                    return resp.json()
                results["failed_api_calls"] += 1
                return None

        for m in merchants:
            if _check_timeout():
                break
            mid = m["merchant_id"]
            customers = customers_by_merchant[mid]
            if not customers:
                continue

            # Check existing payment count
            pay_resp = await _retry_request(
                client.get, f"{BASE_URL}/api/{mid}/payments",
                headers={"X-API-Key": m["api_key"]},
            )
            existing_pay_count = 0
            pay_data = None
            if pay_resp and pay_resp.status_code in (200, 201):
                pay_data = pay_resp.json()
                if isinstance(pay_data, dict):
                    existing_pay_count = pay_data.get("total", 0)
                elif isinstance(pay_data, list):
                    existing_pay_count = len(pay_data)

            if existing_pay_count >= MIN_PAYMENTS_PER_MERCHANT:
                results["skipped_payments"] += existing_pay_count
                # Still need payment records for processing/refunds — fetch a sample
                if pay_data and isinstance(pay_data, dict):
                    payments_by_merchant[mid] = pay_data.get("data", [])[:50]
                elif pay_data and isinstance(pay_data, list):
                    payments_by_merchant[mid] = pay_data[:50]
                continue

            need = random.randint(200, 500)
            tasks = []
            for _ in range(need):
                cust = random.choice(customers)
                tasks.append(_create_payment(m, cust))

            created = await asyncio.gather(*tasks)
            payments_by_merchant[mid] = []
            for pay in created:
                if pay:
                    payments_by_merchant[mid].append(pay)
                    results["payments_created"] += 1

        # ─── Step 4: Process payments (authorize/capture/settle/fail) ──
        captured_payments = []
        settled_payments = []

        async def _process_payment(m, payment):
            async with semaphore:
                roll = random.random()
                pid = payment["payment_id"]
                mid = m["merchant_id"]
                api_key = m["api_key"]
                status_result = None

                if roll < 0.15:
                    resp = await _retry_request(
                        client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/fail",
                        headers={"X-API-Key": api_key},
                    )
                    if resp and resp.status_code in (200, 201):
                        status_result = "failed"
                elif roll < 0.25:
                    resp = await _retry_request(
                        client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/authorize",
                        headers={"X-API-Key": api_key},
                    )
                    if resp and resp.status_code in (200, 201):
                        status_result = "authorized"
                elif roll < 0.40:
                    r1 = await _retry_request(
                        client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/authorize",
                        headers={"X-API-Key": api_key},
                    )
                    if r1 and r1.status_code in (200, 201):
                        r2 = await _retry_request(
                            client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/capture",
                            headers={"X-API-Key": api_key},
                        )
                        if r2 and r2.status_code in (200, 201):
                            status_result = "captured"
                else:
                    r1 = await _retry_request(
                        client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/authorize",
                        headers={"X-API-Key": api_key},
                    )
                    if r1 and r1.status_code in (200, 201):
                        r2 = await _retry_request(
                            client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/capture",
                            headers={"X-API-Key": api_key},
                        )
                        if r2 and r2.status_code in (200, 201):
                            r3 = await _retry_request(
                                client.post, f"{BASE_URL}/api/{mid}/payments/{pid}/settle",
                                headers={"X-API-Key": api_key},
                            )
                            if r3 and r3.status_code in (200, 201):
                                status_result = "settled"

                return (m, payment, status_result)

        tasks = []
        for m in merchants:
            if _check_timeout():
                break
            mid = m["merchant_id"]
            for payment in payments_by_merchant.get(mid, []):
                tasks.append(_process_payment(m, payment))

        if tasks:
            processed = await asyncio.gather(*tasks)
            for m, payment, status in processed:
                if status == "authorized":
                    results["payments_authorized"] += 1
                elif status == "captured":
                    results["payments_captured"] += 1
                    captured_payments.append((m, payment))
                elif status == "settled":
                    results["payments_settled"] += 1
                    settled_payments.append((m, payment))
                elif status == "failed":
                    results["payments_failed"] += 1

        # ─── Step 5: Refunds ───────────────────────────────────────────
        refundable = captured_payments + settled_payments
        num_refunds = min(80, len(refundable) // 3)

        if refundable and num_refunds > 0 and not _check_timeout():
            selected = random.sample(refundable, num_refunds)

            async def _create_refund(m, payment):
                async with semaphore:
                    refund_roll = random.random()
                    if refund_roll < 0.40:
                        refund_amount = float(payment["amount"])
                        refund_type = "full"
                    else:
                        refund_amount = round(random.uniform(5.0, float(payment["amount"]) * 0.8), 2)
                        refund_type = "partial"

                    reason = _generate_refund_reason(m["_config_name"])
                    resp = await _retry_request(
                        client.post,
                        f"{BASE_URL}/api/{m['merchant_id']}/payments/{payment['payment_id']}/refund",
                        json={"amount": refund_amount, "reason": reason},
                        headers={"X-API-Key": m["api_key"]},
                    )
                    if resp and resp.status_code in (200, 201):
                        refund = resp.json()
                        results["refunds_created"] += 1
                        if refund_type == "full":
                            results["full_refunds"] += 1
                        else:
                            results["partial_refunds"] += 1
                        if random.random() < 0.7:
                            await _retry_request(
                                client.post,
                                f"{BASE_URL}/api/{m['merchant_id']}/refunds/{refund['refund_id']}/process",
                                headers={"X-API-Key": m["api_key"]},
                            )
                            results["refunds_processed"] += 1
                        return True
                    results["failed_api_calls"] += 1
                    return False

            refund_tasks = [_create_refund(m, payment) for m, payment in selected]
            await asyncio.gather(*refund_tasks)

    duration = round(time.time() - start_time, 2)
    results["duration_seconds"] = duration
    return results


@router.post("")
async def generate_seed_data(
    merchants: int = Query(default=20, ge=1, le=20),
):
    """Generate realistic seed data through the existing API pipeline.

    Smart seeding — skips levels that already have enough data:
      - If 10+ merchants exist: skips merchant creation
      - If merchant has 1000+ customers: skips customer creation
      - If merchant has 1000+ payments: skips payment creation
    Max duration: 5 minutes (force stops after timeout).
    """
    try:
        results = await _generate_seed_data(merchants)
        return {
            "status": "success",
            "message": f"Generated {results['merchants_created']} merchants, {results['customers_created']} customers, {results['payments_created']} payments, {results['refunds_created']} refunds",
            "data": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed generation failed: {str(e)}")


@router.get("/status")
async def seed_status():
    """Get current data counts from Core DB."""
    from ..database import get_pool
    from ..utils.validators import validate_schema_name

    pool = await get_pool()
    async with pool.acquire() as conn:
        merchant_count = await conn.fetchval("SELECT COUNT(*) FROM public.merchants")
        event_count = await conn.fetchval("SELECT COUNT(*) FROM public.domain_events")
        merchant_data = []
        rows = await conn.fetch("SELECT merchant_id, name, schema_name FROM public.merchants ORDER BY merchant_id")
        for row in rows:
            schema = validate_schema_name(row["schema_name"])
            cust_count = await conn.fetchval(f"SELECT COUNT(*) FROM {schema}.customers")
            pay_count = await conn.fetchval(f"SELECT COUNT(*) FROM {schema}.payments")
            ref_count = await conn.fetchval(f"SELECT COUNT(*) FROM {schema}.refunds")
            merchant_data.append({
                "merchant_id": row["merchant_id"], "name": row["name"],
                "customers": cust_count, "payments": pay_count, "refunds": ref_count,
            })
    return {"total_merchants": merchant_count, "total_events": event_count, "merchants": merchant_data}
