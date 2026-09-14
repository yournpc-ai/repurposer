"""The LLM provider seam (Model 缝, N-42 批⑥): one client per vendor, the
price tables (``PRICING`` / ``price_units`` / ``price_tokens``) living beside
their client. ``base`` holds the vendor-neutral vocabulary — the error types
(``LLMError`` / ``LLMSchemaError``, user_key 税制不动), the capability flags
and the three-tier wire-format law (ADR-077 判词④: 层只换线格式，永不动判决
契约). A second provider lands here (ADR-025's thin interface); the decision
layer never reaches past this seam.
"""
