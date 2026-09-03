"""Bhao item catalog — Bhao's stable item codes for the SPI basket + annex extras.

A owns this file. ``pbs_aliases`` is how a spelling change upstream fails to fork a
series: a raw PBS string is normalised and looked up here. A genuinely new string
gets a NEW code, never a fuzzy merge into an existing one (05-TRACK-A-INGEST.md).

Codes 001–051 are the SPI basket proper (51 items → 17×51 = 867 series). Codes 052+
are Appendix-B/annex extras: same code space, not part of the headline 867.

The prices in this file are the fixture seed levels — obviously synthetic.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ItemDef:
    item_code: str
    item_en: str
    unit_raw: str
    unit_norm: str
    qty_norm: float
    category: str
    spi_weight: float | None
    is_food: bool
    is_administered: bool
    base_price: float  # fixture seed level, PKR
    weekly_sigma: float  # fixture weekly log-volatility
    pbs_aliases: tuple[str, ...]
    notes: str | None = None


ITEMS: tuple[ItemDef, ...] = (
    ItemDef("001", "Wheat Flour Bag 20 Kg", "20 Kg", "kg", 20.0, "grains", 6.65, True, False,
            1450.00, 0.012, ("Wheat Flour Bag 20 Kg",)),
    ItemDef("002", "Wheat Flour Loose 1 Kg", "1 Kg", "kg", 1.0, "grains", 2.10, True, False,
            78.00, 0.014, ("Wheat Flour Loose 1 Kg",)),
    ItemDef("003", "Rice Basmati Broken", "1 Kg", "kg", 1.0, "grains", 1.15, True, False,
            245.00, 0.008, ("Rice Basmati Broken",)),
    ItemDef("004", "Rice IRRI-6", "1 Kg", "kg", 1.0, "grains", 1.85, True, False,
            168.00, 0.008,
            # pathology: item renamed mid-series — both strings map to this code
            ("Rice Irri-6 (Export Quality)", "Rice IRRI-6"),
            "renamed mid-series in fixtures; both aliases resolve to code 004"),
    ItemDef("005", "Bread Plain (Medium)", "Each", "each", 1.0, "grains", 0.55, True, False,
            92.00, 0.010, ("Bread Plain (Medium)", "Bread (Medium Size)")),
    ItemDef("006", "Chapati Plain", "Each", "each", 1.0, "grains", 1.40, True, False,
            18.00, 0.012, ("Chapati Plain", "Chapati / Naan (Plain)")),
    ItemDef("007", "Milk Fresh", "Per Litre", "litre", 1.0, "dairy_eggs", 2.35, True, False,
            212.00, 0.008, ("Milk Fresh", "Milk (Fresh)")),
    ItemDef("008", "Milk Powdered (Tin)", "Each", "each", 1.0, "dairy_eggs", 0.60, True, False,
            2850.00, 0.006, ("Milk Powdered (Tin)", "Milk Powdered Nido Tin")),
    ItemDef("009", "Curd", "1 Kg", "kg", 1.0, "dairy_eggs", 0.45, True, False,
            225.00, 0.010, ("Curd", "Curd (Yoghurt)")),
    ItemDef("010", "Butter Packaged", "Each", "each", 1.0, "dairy_eggs", 0.25, True, False,
            1680.00, 0.007, ("Butter Packaged",)),
    ItemDef("011", "Cooking Oil Branded 5 Litre Tin", "5 Litre", "litre", 5.0, "cooking_oil",
            4.30, True, False, 4380.00, 0.009, ("Cooking Oil Branded 5 Litre Tin",)),
    ItemDef("012", "Vegetable Ghee Branded 2.5 Kg Tin", "2.5 Kg", "kg", 2.5, "cooking_oil",
            1.75, True, False, 2180.00, 0.009, ("Vegetable Ghee Branded 2.5 Kg Tin",)),
    ItemDef("013", "Cooking Oil Loose", "1 Ltr", "litre", 1.0, "cooking_oil", 1.95, True, False,
            628.00, 0.012, ("Cooking Oil Loose", "Oil (Loose)")),
    ItemDef("014", "Chicken Farm Broiler Live", "1 Kg", "kg", 1.0, "meat_poultry", 2.05, True, False,
            385.00, 0.030, ("Chicken Farm Broiler Live", "Chicken (Farm Broiler, Live)")),
    ItemDef("015", "Chicken Farm Broiler Dressed", "1 Kg", "kg", 1.0, "meat_poultry", 0.85, True, False,
            645.00, 0.028, ("Chicken Farm Broiler Dressed", "Chicken Meat (Farm Broiler)")),
    ItemDef("016", "Eggs Farm", "1 Dozen", "dozen", 1.0, "dairy_eggs", 1.30, True, False,
            298.00, 0.022, ("Eggs Farm", "Eggs (Farm)")),
    ItemDef("017", "Beef With Bone", "1 Kg", "kg", 1.0, "meat_poultry", 2.60, True, False,
            825.00, 0.010, ("Beef With Bone", "Beef (With Bone)")),
    ItemDef("018", "Mutton With Bone", "1 Kg", "kg", 1.0, "meat_poultry", 1.05, True, False,
            1780.00, 0.011, ("Mutton With Bone", "Mutton (With Bone)")),
    ItemDef("019", "Onions", "1 Kg", "kg", 1.0, "vegetables", 1.15, True, False,
            125.00, 0.055, ("Onions", "Onion")),
    ItemDef("020", "Tomatoes", "1 Kg", "kg", 1.0, "vegetables", 0.85, True, False,
            98.00, 0.050, ("Tomatoes", "Tomato")),
    ItemDef("021", "Potatoes", "1 Kg", "kg", 1.0, "vegetables", 1.20, True, False,
            72.00, 0.035, ("Potatoes", "Potato"),
            "variance regime shift planted from fixture week 100"),
    ItemDef("022", "Garlic", "1 Kg", "kg", 1.0, "vegetables", 0.30, True, False,
            425.00, 0.030, ("Garlic",)),
    ItemDef("023", "Ginger", "1 Kg", "kg", 1.0, "vegetables", 0.20, True, False,
            535.00, 0.032, ("Ginger",)),
    ItemDef("024", "Peas", "1 Kg", "kg", 1.0, "vegetables", 0.25, True, False,
            185.00, 0.045, ("Peas",), "starts 40 weeks late in fixtures (ragged start)"),
    ItemDef("025", "Carrots", "1 Kg", "kg", 1.0, "vegetables", 0.20, True, False,
            125.00, 0.040, ("Carrots",)),
    ItemDef("026", "Spinach", "1 Kg", "kg", 1.0, "vegetables", 0.15, True, False,
            62.00, 0.050, ("Spinach",)),
    ItemDef("027", "Bananas", "1 Dozen", "dozen", 1.0, "fruit", 0.35, True, False,
            192.00, 0.020, ("Bananas",)),
    ItemDef("028", "Apples Kala Kulu", "1 Kg", "kg", 1.0, "fruit", 0.45, True, False,
            355.00, 0.020, ("Apples Kala Kulu", "Apples (Kala Kulu)")),
    ItemDef("029", "Oranges Malta", "1 Dozen", "dozen", 1.0, "fruit", 0.40, True, False,
            262.00, 0.030, ("Oranges Malta", "Oranges (Malta)")),
    ItemDef("030", "Sugar Refined", "1 Kg", "kg", 1.0, "sugar_sweeteners", 2.35, True, False,
            158.00, 0.015, ("Sugar Refined", "Sugar (Refined)")),
    ItemDef("031", "Gur", "1 Kg", "kg", 1.0, "sugar_sweeteners", 0.20, True, False,
            195.00, 0.018, ("Gur", "Gur (Jaggery)")),
    ItemDef("032", "Tea Packet Branded", "Each", "each", 1.0, "tea_beverages", 1.05, True, False,
            1990.00, 0.007, ("Tea Packet Branded", "Tea (Packet)")),
    ItemDef("033", "Tea Loose Imported", "1 Kg", "kg", 1.0, "tea_beverages", 0.65, True, False,
            1760.00, 0.008, ("Tea Loose Imported", "Tea (Loose)"),
            "Urdu label carries a ZWNJ (unicode pathology)"),
    ItemDef("034", "Salt Iodised", "1 Kg", "kg", 1.0, "spices_condiments", 0.15, True, False,
            46.00, 0.005, ("Salt Iodised", "Salt (Iodised, Powder)")),
    ItemDef("035", "Red Chillies Powder", "1 Kg", "kg", 1.0, "spices_condiments", 0.35, True, False,
            985.00, 0.015, ("Red Chillies Powder", "Chillies (Powder)")),
    ItemDef("036", "Turmeric Powder", "1 Kg", "kg", 1.0, "spices_condiments", 0.10, True, False,
            645.00, 0.012, ("Turmeric Powder", "Turmeric (Powder)")),
    ItemDef("037", "Cumin White Powder", "1 Kg", "kg", 1.0, "spices_condiments", 0.08, True, False,
            1360.00, 0.015, ("Cumin White Powder", "Cumin White (Powder)")),
    ItemDef("038", "Gram Flour Besan", "1 Kg", "kg", 1.0, "pulses", 0.45, True, False,
            252.00, 0.012, ("Gram Flour Besan", "Gram Flour (Besan)")),
    ItemDef("039", "Pulse Gram Washed", "1 Kg", "kg", 1.0, "pulses", 0.55, True, False,
            272.00, 0.014, ("Pulse Gram Washed", "Pulse Gram (Washed)")),
    ItemDef("040", "Pulse Moong Washed", "1 Kg", "kg", 1.0, "pulses", 0.30, True, False,
            292.00, 0.014, ("Pulse Moong Washed",),
            "starts 40 weeks late in fixtures (ragged start)"),
    ItemDef("041", "Pulse Mash Washed", "1 Kg", "kg", 1.0, "pulses", 0.50, True, False,
            388.00, 0.013, ("Pulse Mash Washed",)),
    ItemDef("042", "Pulse Masoor Washed", "1 Kg", "kg", 1.0, "pulses", 0.30, True, False,
            288.00, 0.014, ("Pulse Masoor Washed",),
            "starts 40 weeks late in fixtures (ragged start)"),
    ItemDef("043", "Pulse White Gram Kabuli", "1 Kg", "kg", 1.0, "pulses", 0.20, True, False,
            335.00, 0.015, ("Pulse White Gram Kabuli", "Pulse White Gram (Kabuli)")),
    ItemDef("044", "Match Box", "Each", "each", 1.0, "household", 0.05, False, False,
            2.00, 0.030, ("Match Box", "Match Box (Ten Units)"),
            "the Rs-2 extreme of the scale spread"),
    ItemDef("045", "Toilet Soap Branded 115 gm", "Each", "each", 1.0, "personal_care", 0.30, False, False,
            118.00, 0.006, ("Toilet Soap Branded 115 gm", "Toilet Soap LIFEBUOY 115 gm")),
    ItemDef("046", "Detergent Branded 1 Kg", "Each", "each", 1.0, "household", 0.45, False, False,
            645.00, 0.008, ("Detergent Branded 1 Kg", "Detergent (Surf, 1 Kg)")),
    ItemDef("047", "Petrol Super", "Per Litre", "litre", 1.0, "fuel_energy", 5.85, False, True,
            250.00, 0.0002, ("Petrol Super", "Petrol (Super)"),
            "administered; carries the +18% step change in fixtures"),
    ItemDef("048", "Diesel Hi Speed", "Per Litre", "litre", 1.0, "fuel_energy", 2.40, False, True,
            268.00, 0.0002, ("Diesel Hi Speed", "Diesel (Hi Speed)")),
    ItemDef("049", "Kerosene Oil", "Per Litre", "litre", 1.0, "fuel_energy", 0.10, False, True,
            188.00, 0.0005, ("Kerosene Oil",)),
    ItemDef("050", "Electricity Charges Per Unit", "Per Unit", "kwh", 1.0, "utilities", 4.85, False, True,
            54.00, 0.0002, ("Electricity Charges Per Unit", "Electricity Charges (Average Per Unit)")),
    ItemDef("051", "Gas Charges", "MMBTU", "mmbtu", 1.0, "utilities", 2.05, False, True,
            17000.00, 0.0002, ("Gas Charges",),
            "the Rs-17,000 extreme of the scale spread"),
    # --- Appendix-B / annex extras: same code space, outside the headline 867 ---
    ItemDef("052", "Cell Phone Charges", "Per Minute", "minute", 1.0, "services", None, False, False,
            2.50, 0.002, ("Cell Phone Charges",)),
    ItemDef("053", "Cooked Beef Plate", "Per Plate", "plate", 1.0, "services", None, True, False,
            480.00, 0.010, ("Cooked Beef Plate",)),
    ItemDef("054", "Tea Cup (Hotel)", "Per Cup", "cup", 1.0, "tea_beverages", None, True, False,
            60.00, 0.008, ("Tea Cup (Hotel)",)),
    ItemDef("055", "Gents Chappal", "Pair", "pair", 1.0, "clothing_footwear", None, False, False,
            1250.00, 0.006, ("Gents Chappal",)),
    ItemDef("056", "Cloth Printed Cotton", "1 mtr", "metre", 1.0, "clothing_footwear", None, False, False,
            420.00, 0.006, ("Cloth Printed Cotton",)),
    ItemDef("057", "LPG Cylinder 11.8 Kg", "11.8 Kg", "kg", 11.8, "fuel_energy", None, False, True,
            2780.00, 0.008, ("LPG Cylinder 11.8 Kg",)),
)

# The SPI basket proper (what the weekly national table covers; the headline 867).
SPI_BASKET_CODES = [it.item_code for it in ITEMS if it.item_code <= "051"]

ITEM_BY_CODE: dict[str, ItemDef] = {it.item_code: it for it in ITEMS}


def normalise_name(s: str) -> str:
    """Normalise a raw PBS item string for alias lookup (05-TRACK-A-INGEST.md)."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


ALIAS_INDEX: dict[str, str] = {}
for _it in ITEMS:
    ALIAS_INDEX[normalise_name(_it.item_en)] = _it.item_code
    for _a in _it.pbs_aliases:
        ALIAS_INDEX.setdefault(normalise_name(_a), _it.item_code)

# City-header regex from 03/04 — the "(NN)" suffix is the reliable signal.
CITY_HEADER_RE = re.compile(r"^(?P<name>[A-Za-z\s\.\-']+?)\s*\((?P<code>\d{2})\)$")


def first_week() -> dt.date:
    return dt.date(2023, 8, 31)  # first fixture Thursday


def last_week() -> dt.date:
    return dt.date(2026, 8, 20)  # last fixture Thursday (verified week, 04-DATA-SOURCES)
