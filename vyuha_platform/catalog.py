"""Starter catalogues, and the pictures that go with them.

Setting up stock is the first real work a new business does here, and it is the
point most of them would give up: a blank table with an "Add item" button asks
somebody to type forty rows before the product does anything for them.

So instead the trade they picked chooses a **starter catalogue** — the things a
nursery, a dairy or a hardware shop actually sells, with the unit each is sold
by and a plausible price. They tick what they carry, correct the numbers that
are wrong, and are done in a minute. Nothing here is authoritative; every value
is a starting point they can change, and they can always add their own.

The pictures are generated SVG, not photographs, for the same reasons the trade
backdrops were: they render instantly, work with no internet, never 404, and
cannot show somebody a picture of the wrong thing. A drawing of a sack labelled
"Urea 50kg" is honest in a way a stock photo of *a* sack is not.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------- glyphs

#: One drawing per kind of thing, not per item — a "sack" serves urea, manure
#: and cattle feed alike. Keyed by name so a catalogue row just names its shape.
_PATHS: dict[str, str] = {
    "plant": '<path d="M32 54V30M32 34c-9 0-16-6-16-14 9-1 16 5 16 14Zm0-2c8 0 14-6 14-13-8-1-14 5-14 13Z"/>'
             '<path d="M22 54h20"/>',
    "sapling": '<path d="M32 54V26"/><path d="M32 30c-7-2-11-8-10-15 7 0 12 6 10 15Z"/>'
               '<path d="M24 54h16l-2-8H26Z"/>',
    "sack": '<path d="M20 24h24l4 26a6 6 0 0 1-6 6H22a6 6 0 0 1-6-6Z"/>'
            '<path d="M20 24c2-6 6-8 12-8s10 2 12 8"/><path d="M24 38h16"/>',
    "seed": '<path d="M18 30h28v20a6 6 0 0 1-6 6H24a6 6 0 0 1-6-6Z"/>'
            '<path d="M18 30l4-12h20l4 12"/><circle cx="28" cy="42" r="2.5"/>'
            '<circle cx="36" cy="46" r="2.5"/>',
    "pot": '<path d="M18 26h28l-4 26a6 6 0 0 1-6 5H28a6 6 0 0 1-6-5Z"/><path d="M15 26h34"/>',
    "tool": '<path d="M38 18a8 8 0 0 0-8 10L16 42a4 4 0 0 0 6 6l14-14a8 8 0 0 0 10-8l-6 6-5-1-1-5Z"/>',
    "spray": '<path d="M26 26h14v28a4 4 0 0 1-4 4h-6a4 4 0 0 1-4-4Z"/>'
             '<path d="M28 26v-6h10v6"/><path d="M40 22h8M40 27h6"/>',
    "soil": '<path d="M14 44c6-6 12-6 18 0s12 6 18 0"/><path d="M14 52c6-6 12-6 18 0s12 6 18 0"/>'
            '<circle cx="24" cy="26" r="3"/><circle cx="38" cy="30" r="3"/>',
    "grain": '<path d="M32 54V24"/><path d="M32 28c-6-1-9-5-8-11 6 0 10 4 8 11Z"/>'
             '<path d="M32 38c-6-1-9-5-8-11 6 0 10 4 8 11Z"/>'
             '<path d="M32 28c6-1 9-5 8-11-6 0-10 4-8 11Z"/>'
             '<path d="M32 38c6-1 9-5 8-11-6 0-10 4-8 11Z"/>',
    "milk": '<path d="M26 20h12v6l4 8v22a4 4 0 0 1-4 4H26a4 4 0 0 1-4-4V34l4-8Z"/>'
            '<path d="M22 40h20"/>',
    "bottle": '<path d="M28 16h8v8l5 9v25a4 4 0 0 1-4 4H27a4 4 0 0 1-4-4V33l5-9Z"/>',
    "box": '<path d="M16 26l16-8 16 8v20l-16 8-16-8Z"/><path d="M16 26l16 8 16-8M32 34v20"/>',
    "gear": '<circle cx="32" cy="36" r="8"/><path d="M32 18v6M32 48v6M14 36h6M44 36h6'
            'M19 23l4 4M41 45l4 4M45 23l-4 4M23 45l-4 4"/>',
    "bolt": '<path d="M26 18h12v10l-3 26h-6l-3-26Z"/><path d="M23 22h18"/>',
    "pipe": '<path d="M14 28h22a10 10 0 0 1 0 20H22"/><path d="M14 22v12M14 34h6"/>',
    "paint": '<path d="M20 28h24v24a4 4 0 0 1-4 4H24a4 4 0 0 1-4-4Z"/>'
             '<path d="M20 28c0-5 5-8 12-8s12 3 12 8"/><path d="M44 32h6v10"/>',
    "cloth": '<path d="M22 20l10 6 10-6 8 8-6 6v22H20V34l-6-6Z"/>',
    "pill": '<rect x="18" y="30" width="28" height="14" rx="7"/><path d="M32 30v14"/>',
}

#: Fallback for anything unmapped, so a missing key is a plain box, not a crash.
_FALLBACK = "box"


def glyph(kind: str, accent: str = "currentColor") -> str:
    """One inline SVG, sized by CSS, coloured by the trade's accent."""
    path = _PATHS.get(kind, _PATHS[_FALLBACK])
    return (f'<svg class="glyph" viewBox="0 0 64 64" fill="none" stroke="{accent}" '
            f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{path}</svg>')


# ----------------------------------------------------------------- catalogues

@dataclass(frozen=True)
class Suggestion:
    """One thing a business of this trade probably sells."""

    name: str
    category: str
    unit: str
    rate: float                 # what they'd sell it for — a starting point
    cost: float                 # what it probably cost them
    kind: str                   # which glyph to draw

    @property
    def margin(self) -> float:
        return self.rate - self.cost


def _s(name, category, unit, rate, cost, kind) -> Suggestion:
    return Suggestion(name, category, unit, rate, cost, kind)


#: Prices are indicative Indian retail, deliberately round, and every one is
#: editable before it is saved. They exist to save typing, not to be correct.
STARTERS: dict[str, list[Suggestion]] = {
    "farming": [
        _s("Paddy seed", "Seeds", "kg", 60, 42, "seed"),
        _s("Urea 50kg", "Manure & Fertiliser", "bag", 300, 266, "sack"),
        _s("DAP 50kg", "Manure & Fertiliser", "bag", 1350, 1200, "sack"),
        _s("Farmyard manure", "Manure & Fertiliser", "bag", 180, 120, "sack"),
        _s("Areca nut", "Produce", "kg", 450, 380, "grain"),
        _s("Black pepper", "Produce", "kg", 620, 520, "grain"),
        _s("Coconut", "Produce", "piece", 35, 24, "plant"),
        _s("Pesticide spray 1L", "Pesticides", "litre", 640, 520, "spray"),
    ],
    "nursery": [
        _s("Areca Palm 4ft", "Plants", "piece", 450, 260, "plant"),
        _s("Money Plant", "Plants", "piece", 120, 60, "plant"),
        _s("Rose sapling", "Plants", "piece", 90, 45, "sapling"),
        _s("Mango grafted sapling", "Plants", "piece", 220, 130, "sapling"),
        _s("Vermicompost 5kg", "Manure & Fertiliser", "bag", 180, 110, "sack"),
        _s("Red soil", "Soil & Compost", "bag", 90, 45, "soil"),
        _s("Coco peat block", "Soil & Compost", "piece", 140, 85, "soil"),
        _s("Grow bag 12in", "Pots & Planters", "piece", 45, 22, "pot"),
        _s("Terracotta pot 10in", "Pots & Planters", "piece", 160, 95, "pot"),
        _s("Neem oil 500ml", "Pesticides", "piece", 280, 190, "spray"),
    ],
    "dairy": [
        _s("Cow milk", "Dairy", "litre", 56, 44, "milk"),
        _s("Buffalo milk", "Dairy", "litre", 72, 58, "milk"),
        _s("Curd 500g", "Dairy", "packet", 35, 24, "bottle"),
        _s("Paneer", "Dairy", "kg", 420, 330, "box"),
        _s("Ghee 1L", "Dairy", "bottle", 780, 620, "bottle"),
        _s("Butter 500g", "Dairy", "packet", 290, 235, "box"),
        _s("Cattle feed 50kg", "Feed", "bag", 1250, 1080, "sack"),
    ],
    "kirana": [
        _s("Sona Masoori rice", "Grocery", "kg", 62, 52, "grain"),
        _s("Toor dal", "Grocery", "kg", 165, 140, "grain"),
        _s("Sugar", "Grocery", "kg", 46, 40, "sack"),
        _s("Wheat atta 5kg", "Grocery", "packet", 260, 225, "sack"),
        _s("Sunflower oil 1L", "Grocery", "bottle", 145, 128, "bottle"),
        _s("Tea powder 250g", "Grocery", "packet", 130, 105, "box"),
        _s("Salt 1kg", "Grocery", "packet", 24, 18, "sack"),
        _s("Bath soap", "Household", "piece", 42, 33, "box"),
    ],
    "retail": [
        _s("Cement bag 50kg", "Building", "bag", 420, 380, "sack"),
        _s("Wall paint 4L", "Paint", "piece", 1250, 980, "paint"),
        _s("PVC pipe 1in", "Plumbing", "piece", 210, 160, "pipe"),
        _s("Wire roll 90m", "Electrical", "piece", 1450, 1180, "pipe"),
        _s("Modular switch", "Electrical", "piece", 95, 62, "box"),
        _s("Screws 100pc", "Fasteners", "packet", 130, 88, "bolt"),
        _s("Hammer", "Tools", "piece", 340, 240, "tool"),
    ],
    "manufacturing": [
        _s("Ball bearing 6204", "Bearings", "piece", 340, 250, "gear"),
        _s("Oil seal 35x52", "Seals", "piece", 95, 62, "gear"),
        _s("Flexible coupling", "Transmission", "piece", 1250, 940, "gear"),
        _s("Hex bolt M12", "Fasteners", "piece", 28, 17, "bolt"),
        _s("V-belt B-52", "Transmission", "piece", 420, 300, "gear"),
        _s("Grease 500g", "Consumables", "piece", 260, 190, "bottle"),
    ],
    "distribution": [
        _s("Biscuit carton", "FMCG", "box", 980, 860, "box"),
        _s("Shampoo sachet case", "FMCG", "box", 1450, 1290, "box"),
        _s("Detergent 1kg", "FMCG", "packet", 118, 96, "sack"),
        _s("Cooking oil 15L tin", "FMCG", "piece", 2150, 1980, "bottle"),
        _s("Soap case", "FMCG", "box", 1180, 1030, "box"),
    ],
    "textiles": [
        _s("Cotton saree", "Sarees", "piece", 1450, 950, "cloth"),
        _s("Silk saree", "Sarees", "piece", 6500, 4800, "cloth"),
        _s("Shirt piece", "Fabric", "piece", 620, 420, "cloth"),
        _s("Bedsheet double", "Home linen", "piece", 890, 610, "cloth"),
        _s("Towel", "Home linen", "piece", 240, 155, "cloth"),
    ],
    "pharmacy": [
        _s("Paracetamol 500mg strip", "Medicine", "packet", 22, 16, "pill"),
        _s("Amoxicillin 500 strip", "Medicine", "packet", 96, 72, "pill"),
        _s("ORS sachet", "Medicine", "packet", 22, 15, "packet"),
        _s("Cough syrup 100ml", "Medicine", "bottle", 118, 88, "bottle"),
        _s("Antiseptic 200ml", "Medicine", "bottle", 145, 108, "bottle"),
    ],
    "general": [
        _s("Item A", "Other", "piece", 100, 70, "box"),
        _s("Item B", "Other", "piece", 250, 180, "box"),
        _s("Item C", "Other", "kg", 60, 42, "sack"),
    ],
}


def starters(trade: str) -> list[Suggestion]:
    return STARTERS.get(trade or "general", STARTERS["general"])


def categories(trade: str) -> list[str]:
    """The categories this trade actually uses, in first-seen order."""
    seen: list[str] = []
    for s in starters(trade):
        if s.category not in seen:
            seen.append(s.category)
    return seen


# ------------------------------------------------- artwork for any item name

#: Word to shape, longest phrase first so "cattle feed" beats "feed". A stock
#: list is not built from the starter catalogue — most clients type their own
#: names or arrive with a spreadsheet — so the shape has to be inferable from
#: the words themselves, or every item on the shelf gets the same box.
_WORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("sapling", "seedling", "graft"), "sapling"),
    (("plant", "shrub", "flower", "rose", "tulsi"), "plant"),
    (("seed", "beej"), "seed"),
    (("urea", "dap", "potash", "npk", "mop", "ssp", "fertiliser", "fertilizer",
      "gypsum", "manure", "compost", "cake", "khaad"), "sack"),
    (("cattle feed", "feed", "chunni", "husk", "bran"), "grain"),
    (("grain", "rice", "wheat", "paddy", "jowar", "ragi", "maize"), "grain"),
    (("soil", "cocopeat", "mud", "sand"), "soil"),
    (("pot", "planter", "grow bag", "tray"), "pot"),
    (("spray", "sprayer", "pesticide", "insecticide", "herbicide",
      "fungicide"), "spray"),
    (("pipe", "hose", "drip", "sprinkler", "tubing"), "pipe"),
    (("paint", "primer", "enamel", "distemper"), "paint"),
    (("bolt", "screw", "nail", "nut", "washer", "rivet"), "bolt"),
    (("wire", "rope", "tarpaulin", "sheet", "cloth", "net", "shade"), "cloth"),
    (("motor", "pump", "engine", "bearing", "machine"), "gear"),
    (("tablet", "capsule", "medicine", "vaccine", "tonic"), "pill"),
    (("bottle", "can", "litre", "oil", "lubricant"), "bottle"),
    (("milk", "curd", "ghee", "dairy"), "milk"),
    (("spade", "shovel", "shear", "sickle", "axe", "hammer", "plier",
      "spanner", "tool", "cutter", "trowel", "khurpi"), "tool"),
)

#: Category words, used only when the item name gives nothing away.
_BY_CATEGORY: tuple[tuple[tuple[str, ...], str], ...] = (
    (("fertilis", "fertiliz", "manure", "crop care"), "sack"),
    (("seed",), "seed"),
    (("plant", "nursery"), "plant"),
    (("tool", "implement"), "tool"),
    (("hardware", "fitting"), "bolt"),
    (("feed", "fodder"), "grain"),
    (("dairy",), "milk"),
)


def glyph_for(name: str, category: str = "", accent: str = "currentColor") -> str:
    """The right drawing for an item, worked out from what it is called."""
    return glyph(kind_for(name, category), accent)


def kind_for(name: str, category: str = "") -> str:
    """Which shape an item should wear. Falls back to a plain box, never blank."""
    text = (name or "").lower()
    for words, kind in _WORDS:
        if any(w in text for w in words):
            return kind
    cat = (category or "").lower()
    for words, kind in _BY_CATEGORY:
        if any(w in cat for w in words):
            return kind
    return "box"
