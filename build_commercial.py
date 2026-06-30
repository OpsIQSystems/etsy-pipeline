"""Build a single new premium product: the Commercial Real Estate Deal Analyzer.
Inline opportunity (not added to opportunities.json, so the daily schedule is
untouched). Same Opus pipeline: spec -> live-formula workbook + PDF + listing copy."""
import json
import os

import creator

COMMERCIAL = {
    "what_exists_and_flaws": (
        "Existing commercial RE calculators on Etsy ($79-175) compute cap rate and "
        "cash-on-cash but stop at the numbers. They ignore DSCR (which every commercial "
        "lender requires), don't model NNN vs gross lease expense responsibility, lack "
        "per-square-foot benchmarking, and never tell the investor whether to actually "
        "buy, negotiate, or walk away. None give a goal-aligned verdict."
    ),
    "what_to_build": (
        "A Commercial Real Estate Deal Analyzer that compares 2-5 commercial or mixed-use "
        "deals side by side and delivers a Buy / Negotiate / Pass verdict for each, aligned "
        "to the investor's goal (cash flow vs appreciation). It must compute and use: NOI, "
        "cap rate, cash-on-cash return, DSCR (debt service coverage ratio), price per square "
        "foot vs an asset-class benchmark, loan constant, and break-even occupancy. It must "
        "handle lease structure (NNN / Modified Gross / Full-Service Gross) so operating "
        "expense responsibility is modeled correctly, and flag any deal where DSCR falls "
        "below the lender threshold (about 1.25x) or price per square foot exceeds the "
        "market benchmark. NOI must be computed the way a real credit committee does it: "
        "effective gross income minus landlord operating expenses minus a replacement/"
        "capital-expenditure reserve (entered in dollars per square foot) minus a property "
        "management fee (entered as a percent of effective gross income) - so the cash flow "
        "is not overstated. Break-even occupancy must include those costs. The verdict must "
        "also flag a Negotiate on any deal with vacancy above ~15% (lease-up risk) regardless "
        "of the investor's goal. The verdict/recommendation column MUST be a live nested-IF "
        "formula, never static text. Include input columns for: Property Name, Asset Type, "
        "Square Footage, Purchase Price, Gross Rental Income, Vacancy %, Operating Expenses, "
        "Capital Reserve $/SqFt, Management Fee %, Lease Type, Loan Amount, Interest Rate, "
        "Amortization Years, and Target DSCR."
    ),
    "ai_explanation_value": (
        "Turns the four metrics commercial lenders and brokers actually use (NOI, cap rate, "
        "DSCR, price/SqFt) into a plain-English call. Example: 'Deal B: DSCR of 1.18x is "
        "below the 1.25x most lenders require, and price/SqFt of $214 is 12% above the "
        "submarket median of $191 - the financing will not pencil at this price. Negotiate "
        "toward $1.95M or pass.' No commercial-finance background required."
    ),
    "suggested_price": 149,
    "suggested_etsy_title": (
        "Commercial Real Estate Deal Analyzer | NNN Lease DSCR Cap Rate Calculator | "
        "Buy or Pass Decision Tool for Investors Google Sheets"
    ),
    "target_customer": (
        "Commercial real estate investors, brokers, and agents evaluating retail, office, "
        "industrial, or mixed-use income properties; and residential investors moving up "
        "into small commercial or multifamily deals."
    ),
    "score": 9,
}


def main():
    os.makedirs(creator.PRODUCTS_DIR, exist_ok=True)
    os.makedirs(creator.LISTINGS_DIR, exist_ok=True)
    client = creator.load_anthropic_client()
    opp = COMMERCIAL
    title = opp["suggested_etsy_title"]
    print(f"[*] Building: {title}\n")

    print("  [-] Requesting dashboard spec from Claude (Opus)...")
    spec = creator.call_claude_json(
        client, creator.SPEC_SYSTEM_PROMPT,
        f"Design the dashboard for this opportunity:\n{json.dumps(opp, indent=2)}",
        max_tokens=8192,
    )
    print("  [-] Requesting Etsy listing copy from Claude...")
    listing_copy = creator.call_claude_json(
        client, creator.LISTING_SYSTEM_PROMPT,
        f"Write Etsy listing copy for this opportunity:\n{json.dumps(opp, indent=2)}",
        max_tokens=2048,
    )

    fname_base = creator.safe_filename(title)
    xlsx_path = os.path.join(creator.PRODUCTS_DIR, f"{fname_base}.xlsx")
    pdf_path = os.path.join(creator.PRODUCTS_DIR, f"{fname_base}_guide.pdf")
    listing_path = os.path.join(creator.LISTINGS_DIR, f"{fname_base}.txt")

    print(f"  [-] Building workbook -> {xlsx_path}")
    creator.build_workbook(spec, opp, xlsx_path)
    print(f"  [-] Building PDF guide -> {pdf_path}")
    creator.build_pdf_guide(spec, opp, pdf_path)
    print(f"  [-] Writing listing copy -> {listing_path}")
    creator.build_listing_txt(listing_copy, opp, listing_path)
    print(f"\n[done] Commercial analyzer built. fname_base = {fname_base}")


if __name__ == "__main__":
    main()
