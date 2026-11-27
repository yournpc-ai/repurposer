"""PostgreSQL ranking for the permanent music and voice libraries."""

from sqlalchemy import case, func, or_, select

from app.models.tables import Music, Voice


async def search_audio(
    db,
    model,
    owner_id,
    *,
    query,
    style,
    limit,
    mood=None,
    tags=None,
    language=None,
    tone=None,
    bpm=None,
    energy=None,
    genre=None,
    pacing=None,
    instrumental_only=False,
):
    music = model is Music
    owner = model.generated_by_user_id if music else model.owner_id
    public = (
        or_(Music.scope == "platform", Music.is_public.is_(True))
        if music
        else model.scope == "platform"
    )
    stmt = select(model).where(
        model.status.in_(("curated", "ready")),
        or_(public, owner == owner_id) if owner_id else public,
    )
    for field, value in (("energy", energy), ("genre", genre), ("bpm", bpm), ("pacing", pacing)):
        if value is not None:
            stmt = stmt.where(getattr(model, field) == value)
    if instrumental_only:
        stmt = stmt.where(Music.instrumental.is_(True))
    if language:
        # Match both language codes and their region-specific variants.
        langs = func.jsonb_array_elements_text(Voice.languages).table_valued("value").alias("lang")
        stmt = stmt.where(
            select(1)
            .select_from(langs)
            .where(langs.c.value.istartswith(language, autoescape=True))
            .exists()
        )
    doc = model.search_text
    # When browsing the full music library without an explicit filter, surface
    # curated platform tracks evenly instead of letting one high-use_count
    # user track dominate every future project.
    if music and not (query or mood or tags or style or genre or energy or bpm):
        score = case((Music.scope == "platform", 1.0), else_=0.0)
    else:
        score = 0.3 * func.ln(1 + model.use_count)
    fields = model.tags if music else model.tone_tags
    for needle, column in ((style, model.compatible_styles), (tone, fields)):
        if needle:
            hit = column.contains([needle.lower()])
            stmt = stmt.where(or_(hit, doc.icontains(needle, autoescape=True)))
            score += case((hit, 4.0), else_=2.0)
    if mood:
        hit = Music.mood.ilike(mood)
        stmt = stmt.where(or_(hit, doc.icontains(mood, autoescape=True)))
        score += case((hit, 5.0), else_=3.0)
    if tags:
        terms = [doc.icontains(t, autoescape=True) for t in tags if t.strip()]
        if terms:
            stmt = stmt.where(or_(*terms))
            score += sum(case((hit, 4.0), else_=0.0) for hit in terms)
    if query and query.strip():
        terms = [doc.icontains(t, autoescape=True) for t in query.split()]
        stmt = stmt.where(or_(doc.op("%")(query), *terms))
        score += 2.5 * func.similarity(doc, query) + sum(
            case((hit, 3.0), else_=0.0) for hit in terms
        )
    rows = await db.scalars(
        stmt.order_by(score.desc(), model.is_favorite.desc(), model.id.asc()).limit(
            max(1, min(100, limit))
        )
    )
    return list(rows)
