"""One-off: regenerate ONLY the listing copy (title/description/tags) for every
opportunity, using the tightened tag-length prompt, then hard-enforce the
20-char limit programmatically as a safety net in case Claude still misses."""
import json
import os

import creator

with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
    opportunities = json.load(f)

client = creator.load_anthropic_client()
print(f"[*] Regenerating listing copy for {len(opportunities)} products...\n")

fixed = 0
for idx, opportunity in enumerate(opportunities, start=1):
    title = opportunity.get("suggested_etsy_title", f"opportunity_{idx}")
    print(f"[{idx}/{len(opportunities)}] {title[:70]}")
    try:
        listing_copy = creator.call_claude_json(
            client, creator.LISTING_SYSTEM_PROMPT,
            f"Write Etsy listing copy for this opportunity:\n{json.dumps(opportunity, indent=2)}",
            max_tokens=2048,
        )

        # Safety net: hard-truncate any tag Claude still got wrong, at a word boundary.
        clean_tags = []
        for tag in listing_copy.get("tags", []):
            if len(tag) <= 20:
                clean_tags.append(tag)
                continue
            words = tag.split()
            truncated = ""
            for w in words:
                candidate = (truncated + " " + w).strip()
                if len(candidate) <= 20:
                    truncated = candidate
                else:
                    break
            clean_tags.append(truncated or tag[:20])
        listing_copy["tags"] = clean_tags

        fname_base = creator.safe_filename(title)
        listing_path = os.path.join(creator.LISTINGS_DIR, f"{fname_base}.txt")
        creator.build_listing_txt(listing_copy, opportunity, listing_path)
        fixed += 1
        print("  [+] Done.")
    except Exception as e:
        print(f"  [error] {e}")
        continue

print(f"\n[done] Fixed listing copy for {fixed}/{len(opportunities)} products.")
