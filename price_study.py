import csv

rows = list(csv.DictReader(open("listings.csv", encoding="utf-8")))
groups = {
    "CREW/FIELD SERVICE (#1)": ["crew profit tracker", "technician scorecard", "landscaping KPI tracker",
        "service business dashboard", "job cost calculator", "route profitability tracker",
        "crew performance dashboard", "technician KPI tracker", "field ops scorecard",
        "service company profit tracker", "contractor business dashboard",
        "equipment maintenance tracker", "field service business dashboard", "HVAC business spreadsheet"],
    "RENTAL/LANDLORD (#2)": ["property management template", "landlord tracker", "rental spreadsheet",
        "rent tracker google sheets"],
    "TENANT (#5)": ["tenant checklist"],
    "MAINTENANCE (#4)": ["maintenance log", "work order template"],
}

for label, kws in groups.items():
    items = []
    for r in rows:
        if r["keyword"] in kws:
            try:
                p = float(r["price"])
                if 0 < p < 500:
                    items.append((p, r["title"], r["rating"], r["listing_id"]))
            except ValueError:
                pass
    items.sort(reverse=True)
    print(f"=== {label} : top 8 by price ===")
    for p, title, rating, lid in items[:8]:
        print(f"  ${p:.2f} (rating {rating}) {title[:90]}")
    print()
