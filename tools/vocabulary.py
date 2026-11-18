"""Invented items and suppliers used to build synthetic training lines and documents.

IMPORTANT: these band labels are ILLUSTRATIVE. They exist so the classifier has something to learn
and the tests have known answers; they are not tax advice. The label for each item type is the
band to claim, where 0 also covers VAT that cannot be reclaimed. Check them against your own
bookkeeping practice and Revenue's guidance, and edit this file if one is wrong: nothing else in
the code depends on any particular label.

All supplier names are made up. No real business, customer or invoice is used."""

# band key -> item type -> phrases that could appear on a line
ITEMS: dict[str, dict[str, list[str]]] = {
    "23": {
        "stationery": ["A4 copy paper", "ballpoint pens", "stapler", "lever arch files", "envelopes DL",
                       "sticky notes", "printer paper 80gsm", "whiteboard markers", "ring binders"],
        "print supplies": ["toner cartridge", "ink cartridge black", "printer ink colour", "label rolls"],
        "it equipment": ["usb cable", "wireless mouse", "keyboard", "monitor 24 inch", "laptop charger",
                         "external hard drive", "hdmi cable", "webcam"],
        "software": ["software licence annual", "antivirus subscription", "cloud storage plan",
                     "domain renewal", "web hosting"],
        "furniture": ["office chair", "desk lamp", "filing cabinet", "desk organiser"],
        "hardware": ["cordless drill", "screwdriver set", "light bulbs led", "extension lead",
                     "paint brushes", "padlock", "tape measure"],
        "cleaning goods": ["washing up liquid", "bleach", "bin liners", "multi surface cleaner",
                           "paper towels", "toilet roll"],
        "services": ["accountancy fee", "legal fee", "consultancy day rate", "design services",
                     "advertising online", "printing business cards", "courier delivery"],
        "vehicle parts": ["wiper blades", "car battery", "brake pads", "engine oil 5l", "tyre fitted"],
    },
    "13.5": {
        "energy": ["electricity charges", "gas supply", "heating oil delivery", "briquettes", "bagged coal",
                   "kerosene 500 litres", "standing charge electricity"],
        "building work": ["plumbing repair labour", "electrician call out", "roof repair", "plastering",
                          "building maintenance", "window repair", "painting and decorating labour"],
        "cleaning service": ["office cleaning service", "window cleaning", "carpet cleaning service",
                             "deep clean premises"],
        "repairs": ["car service labour", "van repair", "equipment repair labour", "boiler service"],
        "other 13.5": ["vet consultation", "car hire 3 days", "hairdressing", "skip hire"],
    },
    "9": {
        "publications": ["newspaper", "irish times", "magazine monthly", "periodical subscription",
                         "ebook download", "weekly magazine"],
        "entertainment": ["cinema ticket", "theatre ticket", "concert ticket", "museum entry",
                          "swimming pool entry", "gym day pass"],
        "other 9": ["live music ticket", "sports facility hire", "gallery admission"],
    },
    "0": {
        "road fuel": ["unleaded petrol", "diesel", "petrol 95", "green diesel", "fuel pump 4", "premium diesel",
                      "unleaded 95", "auto diesel"],
        "basic food": ["bread", "milk 2 litres", "eggs dozen", "butter", "bananas", "brown bread",
                       "potatoes", "fresh milk", "porridge oats"],
        "meals out": ["client lunch", "staff lunch", "restaurant meal", "dinner with client",
                      "breakfast meeting", "team meal"],
        "accommodation": ["hotel room one night", "bed and breakfast", "guest house stay",
                          "overnight accommodation"],
        "exempt": ["postage stamps", "insurance premium", "bank charges", "rent payment", "parking fine",
                   "childrens book", "school books", "stamp duty", "toll charge"],
    },
}

# Suppliers (invented). Each list is the kind of business that tends to supply those items.
SUPPLIERS: dict[str, list[str]] = {
    "fuel": ["Corrib Fuels", "Lee Valley Service Station", "Slieve Road Garage", "Atlantic Forecourt",
             "Shannonside Petrol", "Kerry Roadside Fuels"],
    "office": ["Lee Valley Stationery", "Corrib Office Supplies", "Greenway Print and Paper",
               "Harbour IT Supplies", "Brindle Business Centre", "Mallow Computer Store"],
    "utility": ["Hollow Glen Energy", "Munster Gas Supply", "Blackwater Power", "Southern Heat Oils"],
    "trade": ["Dunmore Builders Merchants", "Cahir Plumbing Services", "Rathmore Electrical",
              "Glenview Maintenance", "Tralee Roofing Ltd", "Clean Sweep Cleaning"],
    "shop": ["Quay Street News", "Daly's Corner Shop", "Fairhill Convenience", "Westbridge Newsagents",
             "Mill Lane Supermarket", "Greenfield Foods"],
    "leisure": ["Harbour Cinema", "Old Mill Theatre", "Riverside Leisure Centre", "Cobh Museum"],
    "hospitality": ["The Anchor Inn", "Bridge Street Cafe", "Linden House Hotel", "The Corner Table",
                    "Seaview Guest House"],
    "services": ["Murphy Hegarty Accountants", "Brennan Design Studio", "Fastlane Couriers",
                 "Kinsale Web Services", "O'Neill Legal"],
    "motor": ["Ballincollig Motor Factors", "Rapid Tyres", "Eastside Auto Parts", "Bandon Vehicle Services"],
}

# which supplier groups usually supply which item types
TYPE_SUPPLIERS: dict[str, list[str]] = {
    "stationery": ["office"], "print supplies": ["office"], "it equipment": ["office"],
    "software": ["office", "services"], "furniture": ["office"], "hardware": ["trade", "shop"],
    "cleaning goods": ["shop", "trade"], "services": ["services"], "vehicle parts": ["motor"],
    "energy": ["utility"], "building work": ["trade"], "cleaning service": ["trade"],
    "repairs": ["motor", "trade"], "other 13.5": ["services", "trade"],
    "publications": ["shop"], "entertainment": ["leisure"], "other 9": ["leisure"],
    "road fuel": ["fuel"], "basic food": ["shop"], "meals out": ["hospitality"],
    "accommodation": ["hospitality"], "exempt": ["services", "shop"],
}

ADDRESS_LINES = ["Main Street", "Quay Road", "Market Square", "Church Hill", "Station Road", "Mill Lane",
                 "Bridge Street", "Harbour View"]
TOWNS = ["Killarney", "Cork", "Tralee", "Mallow", "Kinsale", "Limerick", "Dingle", "Bandon"]
