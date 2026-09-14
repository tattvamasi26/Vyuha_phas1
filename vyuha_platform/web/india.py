"""States and union territories with their GST state codes.

``Client.state`` holds the two-letter code, because that is what decides CGST + SGST
against IGST on an invoice (``invoice.from_sales``). The name is for people.
"""

from __future__ import annotations

STATES: tuple[tuple[str, str], ...] = (
    ("AN", "Andaman & Nicobar Islands"), ("AP", "Andhra Pradesh"),
    ("AR", "Arunachal Pradesh"), ("AS", "Assam"), ("BR", "Bihar"), ("CH", "Chandigarh"),
    ("CG", "Chhattisgarh"), ("DN", "Dadra & Nagar Haveli and Daman & Diu"), ("DL", "Delhi"),
    ("GA", "Goa"), ("GJ", "Gujarat"), ("HR", "Haryana"), ("HP", "Himachal Pradesh"),
    ("JK", "Jammu & Kashmir"), ("JH", "Jharkhand"), ("KA", "Karnataka"), ("KL", "Kerala"),
    ("LA", "Ladakh"), ("LD", "Lakshadweep"), ("MP", "Madhya Pradesh"), ("MH", "Maharashtra"),
    ("MN", "Manipur"), ("ML", "Meghalaya"), ("MZ", "Mizoram"), ("NL", "Nagaland"),
    ("OD", "Odisha"), ("PY", "Puducherry"), ("PB", "Punjab"), ("RJ", "Rajasthan"),
    ("SK", "Sikkim"), ("TN", "Tamil Nadu"), ("TS", "Telangana"), ("TR", "Tripura"),
    ("UP", "Uttar Pradesh"), ("UK", "Uttarakhand"), ("WB", "West Bengal"),
)
CODES = {code for code, _ in STATES}
NAME = dict(STATES)

MONTHS: tuple[tuple[int, str], ...] = (
    (1, "January"), (2, "February"), (3, "March"), (4, "April"), (5, "May"), (6, "June"),
    (7, "July"), (8, "August"), (9, "September"), (10, "October"), (11, "November"),
    (12, "December"),
)
