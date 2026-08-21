"""The LLM provider seam (Model 缝, N-42 批⑥): one client per vendor, the
price tables (``PRICING`` / ``price_units`` / ``price_tokens``) living beside
their client. A second provider lands here (ADR-025's thin interface); the
decision layer never reaches past this seam.
"""
